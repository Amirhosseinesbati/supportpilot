"""Durable ticket connector delivery with reconciliation after ambiguous writes."""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .adapters import AmbiguousWrite, support_for
from .models import ActionLedger, Ticket, now, uid


class TicketSyncError(RuntimeError):
    pass


class TicketSyncInProgress(TicketSyncError):
    pass


def sync_ticket(db: Session, ticket: Ticket) -> Ticket:
    locked = db.scalar(select(Ticket).where(Ticket.id == ticket.id,
                                            Ticket.workspace_id == ticket.workspace_id).with_for_update())
    if locked is None:
        raise TicketSyncError("Local ticket disappeared before synchronization")
    ticket = locked
    if ticket.sync_status == "complete" and ticket.external_ticket_id:
        return ticket
    action_key = f"ticket:{ticket.workspace_id}:{ticket.id}"
    ledger = db.scalar(select(ActionLedger).where(ActionLedger.action_key == action_key).with_for_update())
    if ledger and ledger.status == "complete":
        if not ticket.external_ticket_id:
            raise TicketSyncError("Completed ticket ledger lacks provider ID; reconcile before retry")
        ticket.sync_status = "complete"
        db.commit()
        return ticket
    if ledger and ledger.status == "claimed" and ledger.lease_until and \
            ledger.lease_until.replace(tzinfo=None) > now().replace(tzinfo=None):
        raise TicketSyncInProgress("Ticket synchronization is already in progress")
    external_id = f"supportpilot:{ticket.workspace_id}:{ticket.id}"
    lease_until = now() + timedelta(minutes=5)
    if not ledger:
        ledger = ActionLedger(id=uid(), workspace_id=ticket.workspace_id,
                              action_key=action_key, status="claimed",
                              request_payload={"ticket_id": ticket.id, "external_id": external_id},
                              result_payload=None, lease_until=lease_until)
        db.add(ledger)
    else:
        ledger.status = "claimed"
        ledger.lease_until = lease_until
    ticket.sync_status = "claimed"
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise TicketSyncInProgress("A concurrent ticket synchronization is in progress") from error
    body = "\n".join((ticket.summary,
        f"Verified order context: {json.dumps(ticket.order_context, default=str)}",
        f"Attempted steps: {', '.join(ticket.attempted_steps)}",
        f"Unresolved: {', '.join(ticket.unresolved_questions)}",
        f"Evidence references: {', '.join(str(item.get('chunk_id', '')) for item in ticket.evidence)}"))
    try:
        provider_id = support_for().create_ticket(subject=ticket.subject, body=body,
                                                   external_id=external_id)
    except AmbiguousWrite as error:
        ledger.status = "uncertain"
        ledger.lease_until = None
        ticket.sync_status = "uncertain"
        db.commit()
        raise TicketSyncError("Provider outcome is uncertain; retry will reconcile by external ID") from error
    except Exception as error:
        ledger.status = "failed"
        ledger.lease_until = None
        ticket.sync_status = "failed"
        db.commit()
        raise TicketSyncError("Ticket connector failed; local ticket remains available") from error
    ticket.external_ticket_id = provider_id
    ticket.sync_status = "complete"
    ledger.status = "complete"
    ledger.lease_until = None
    ledger.result_payload = {"provider_ticket_id": provider_id}
    db.commit()
    return ticket
