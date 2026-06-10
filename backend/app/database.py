from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine, desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class AccountRecord(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    starting_equity: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PositionRecord(Base):
    __tablename__ = "positions"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(8), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FillRecord(Base):
    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass
class LoadedState:
    cash: float
    starting_equity: float
    positions: Dict[str, Dict[str, Any]]
    open_orders: Dict[str, Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]
    recent_fills: List[Dict[str, Any]]
    deduped_orders: Dict[str, Dict[str, Any]]


class PersistenceStore:
    def __init__(self, database_url: str, account_id: str = "demo") -> None:
        self.database_url = database_url
        self.account_id = account_id
        self.engine = self._create_engine(database_url)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @classmethod
    def from_env(cls) -> Optional["PersistenceStore"]:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return None
        return cls(database_url=database_url, account_id=os.getenv("ACCOUNT_ID", "demo"))

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def bootstrap_defaults(
        self,
        cash: float,
        starting_equity: float,
        positions: Iterable[Dict[str, Any]],
    ) -> None:
        self.create_schema()
        now = self._now()

        with self.session_factory.begin() as session:
            account = session.get(AccountRecord, self.account_id)
            if account is None:
                session.add(
                    AccountRecord(
                        id=self.account_id,
                        name="Demo Trading Account",
                        cash=cash,
                        starting_equity=starting_equity,
                        updated_at=now,
                    )
                )

            has_positions = (
                session.execute(select(PositionRecord).where(PositionRecord.account_id == self.account_id).limit(1))
                .scalars()
                .first()
                is not None
            )
            if not has_positions:
                for position in positions:
                    session.add(
                        PositionRecord(
                            account_id=self.account_id,
                            symbol=str(position["symbol"]),
                            quantity=int(position["quantity"]),
                            avg_cost=float(position["avg_cost"]),
                            realized_pnl=float(position["realized_pnl"]),
                            updated_at=now,
                        )
                    )

    def load_state(self) -> LoadedState:
        with self.session_factory() as session:
            account = session.get(AccountRecord, self.account_id)
            if account is None:
                raise RuntimeError("Persistence store was not bootstrapped before load_state")

            positions = {
                record.symbol: {
                    "symbol": record.symbol,
                    "quantity": record.quantity,
                    "avg_cost": record.avg_cost,
                    "realized_pnl": record.realized_pnl,
                }
                for record in session.execute(
                    select(PositionRecord).where(PositionRecord.account_id == self.account_id)
                ).scalars()
            }

            recent_orders = [
                self._order_to_dict(record)
                for record in session.execute(
                    select(OrderRecord)
                    .where(OrderRecord.account_id == self.account_id)
                    .order_by(desc(OrderRecord.created_at))
                    .limit(24)
                ).scalars()
            ]

            recent_fills = [
                self._fill_to_dict(record)
                for record in session.execute(
                    select(FillRecord)
                    .where(FillRecord.account_id == self.account_id)
                    .order_by(desc(FillRecord.created_at))
                    .limit(18)
                ).scalars()
            ]

            open_orders = {
                record.id: self._order_to_dict(record)
                for record in session.execute(
                    select(OrderRecord)
                    .where(OrderRecord.account_id == self.account_id, OrderRecord.status == "OPEN")
                    .order_by(desc(OrderRecord.created_at))
                ).scalars()
            }

            fills_by_order = {fill["order_id"]: fill for fill in recent_fills}
            deduped_orders = {}
            for order in recent_orders:
                client_order_id = order.get("client_order_id")
                if client_order_id:
                    deduped_orders[str(client_order_id)] = {
                        "accepted": True,
                        "reason": None,
                        "order": order,
                        "fill": fills_by_order.get(order["id"]),
                    }

            return LoadedState(
                cash=account.cash,
                starting_equity=account.starting_equity,
                positions=positions,
                open_orders=open_orders,
                recent_orders=recent_orders,
                recent_fills=recent_fills,
                deduped_orders=deduped_orders,
            )

    def find_response_by_client_order_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        with self.session_factory() as session:
            order_record = session.execute(
                select(OrderRecord).where(
                    OrderRecord.account_id == self.account_id,
                    OrderRecord.client_order_id == client_order_id,
                )
            ).scalar_one_or_none()
            if order_record is None:
                return None

            fill_record = session.execute(
                select(FillRecord)
                .where(FillRecord.account_id == self.account_id, FillRecord.order_id == order_record.id)
                .order_by(desc(FillRecord.created_at))
                .limit(1)
            ).scalar_one_or_none()

            return {
                "accepted": True,
                "reason": None,
                "order": self._order_to_dict(order_record),
                "fill": self._fill_to_dict(fill_record) if fill_record else None,
            }

    def save_execution(
        self,
        order: Dict[str, Any],
        fill: Optional[Dict[str, Any]],
        cash: float,
        positions: Iterable[Dict[str, Any]],
    ) -> None:
        now = self._now()

        with self.session_factory.begin() as session:
            account = session.get(AccountRecord, self.account_id)
            if account is None:
                account = AccountRecord(
                    id=self.account_id,
                    name="Demo Trading Account",
                    cash=cash,
                    starting_equity=cash,
                    updated_at=now,
                )
                session.add(account)
            else:
                account.cash = cash
                account.updated_at = now

            order_record = session.get(OrderRecord, str(order["id"]))
            if order_record is None:
                session.add(self._order_from_dict(order, now))
            else:
                self._update_order_record(order_record, order, now)

            if fill is not None and session.get(FillRecord, str(fill["id"])) is None:
                session.add(self._fill_from_dict(fill))

            for position in positions:
                symbol = str(position["symbol"])
                position_record = session.get(PositionRecord, {"account_id": self.account_id, "symbol": symbol})
                if position_record is None:
                    session.add(
                        PositionRecord(
                            account_id=self.account_id,
                            symbol=symbol,
                            quantity=int(position["quantity"]),
                            avg_cost=float(position["avg_cost"]),
                            realized_pnl=float(position["realized_pnl"]),
                            updated_at=now,
                        )
                    )
                else:
                    position_record.quantity = int(position["quantity"])
                    position_record.avg_cost = float(position["avg_cost"])
                    position_record.realized_pnl = float(position["realized_pnl"])
                    position_record.updated_at = now

    def _create_engine(self, database_url: str) -> Engine:
        engine_kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in database_url:
                engine_kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **engine_kwargs)

    def _order_from_dict(self, order: Dict[str, Any], updated_at: datetime) -> OrderRecord:
        return OrderRecord(
            id=str(order["id"]),
            account_id=self.account_id,
            client_order_id=order.get("client_order_id"),
            symbol=str(order["symbol"]),
            side=str(order["side"]),
            order_type=str(order["order_type"]),
            quantity=int(order["quantity"]),
            remaining_quantity=int(order["remaining_quantity"]),
            price=float(order["price"]) if order.get("price") is not None else None,
            status=str(order["status"]),
            created_at=self._parse_datetime(order["created_at"]),
            updated_at=updated_at,
        )

    def _update_order_record(self, record: OrderRecord, order: Dict[str, Any], updated_at: datetime) -> None:
        record.remaining_quantity = int(order["remaining_quantity"])
        record.price = float(order["price"]) if order.get("price") is not None else None
        record.status = str(order["status"])
        record.updated_at = updated_at

    def _fill_from_dict(self, fill: Dict[str, Any]) -> FillRecord:
        return FillRecord(
            id=str(fill["id"]),
            account_id=self.account_id,
            order_id=str(fill["order_id"]),
            symbol=str(fill["symbol"]),
            side=str(fill["side"]),
            quantity=int(fill["quantity"]),
            price=float(fill["price"]),
            notional=float(fill["notional"]),
            created_at=self._parse_datetime(fill["created_at"]),
        )

    @staticmethod
    def _order_to_dict(record: OrderRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "client_order_id": record.client_order_id,
            "symbol": record.symbol,
            "side": record.side,
            "order_type": record.order_type,
            "quantity": record.quantity,
            "remaining_quantity": record.remaining_quantity,
            "price": round(record.price, 2) if record.price is not None else None,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _fill_to_dict(record: FillRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "order_id": record.order_id,
            "symbol": record.symbol,
            "side": record.side,
            "quantity": record.quantity,
            "price": round(record.price, 2),
            "notional": round(record.notional, 2),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
