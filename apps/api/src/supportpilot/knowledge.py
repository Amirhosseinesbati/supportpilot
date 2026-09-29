from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Chunk, Document, DocumentVersion, IngestionJob, Message, Workspace, now, uid

TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*", re.I)
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=850, chunk_overlap=125)
ALLOWED = {".pdf": "pdf", ".md": "markdown", ".csv": "csv"}
ALLOWED_AUTHORITIES = {"official_policy", "product_manual", "faq", "support_guide", "uploaded"}


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_title: str
    version: int
    section: str
    page: int | None
    passage: str
    score: float
    category: str
    authority: str
    effective_from: str | None

    def citation(self) -> dict:
        return {"chunk_id": self.chunk_id, "document_title": self.document_title,
                "version": self.version, "section": self.section, "page": self.page,
                "passage": self.passage}


def tokens(value: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN.finditer(value)]


def embedding(value: str) -> list[float]:
    """Deterministic local hashed vector; connected deployments may replace this adapter."""
    vector = [0.0] * 64
    for word in tokens(value):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % 64
        vector[index] += -1.0 if digest[4] % 2 else 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def split_source_text(value: str) -> list[str]:
    parts = SPLITTER.split_text(value)
    if len(parts) > 1 and len(parts[0].strip()) < 80:
        parts[1] = parts[0].strip() + "\n" + parts[1]
        parts.pop(0)
    return [part for part in parts if len(part.strip()) >= 20]


def extract_sections(kind: str, raw: bytes) -> list[LCDocument]:
    if kind == "pdf":
        reader = PdfReader(io.BytesIO(raw))
        if len(reader.pages) > 250:
            raise ValueError("PDF exceeds 250 pages")
        return [LCDocument(page.extract_text() or "", metadata={"section": f"Page {index + 1}", "page": index + 1})
                for index, page in enumerate(reader.pages) if (page.extract_text() or "").strip()]
    decoded = raw.decode("utf-8-sig")
    if kind == "csv":
        rows = list(csv.DictReader(io.StringIO(decoded)))
        if len(rows) > 5000:
            raise ValueError("CSV exceeds 5,000 rows")
        return [LCDocument("; ".join(f"{key}: {value}" for key, value in row.items() if value),
                           metadata={"section": f"Row {index + 2}", "page": None})
                for index, row in enumerate(rows, start=0)]
    current = "Overview"
    sections: list[LCDocument] = []
    lines: list[str] = []
    for line in decoded.splitlines():
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            if lines:
                sections.append(LCDocument("\n".join(lines), metadata={"section": current, "page": None}))
            current = line.lstrip("# ").strip() or "Untitled"
            lines = [line]
        else:
            lines.append(line)
    if lines:
        sections.append(LCDocument("\n".join(lines), metadata={"section": current, "page": None}))
    return [section for section in sections if section.page_content.strip()]


def add_document(db: Session, *, workspace_id: str, filename: str, raw: bytes,
                 category: str = "general", document_id: str | None = None,
                 authority: str | None = None,
                 effective_from: datetime | None = None,
                 effective_to: datetime | None = None) -> tuple[Document, IngestionJob]:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("Only PDF, Markdown, and CSV are accepted")
    if not raw or len(raw) > settings.max_upload_bytes:
        raise ValueError(f"File must be between 1 byte and {settings.max_upload_bytes} bytes")
    if extension == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    if extension != ".pdf":
        raw.decode("utf-8-sig")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", category):
        raise ValueError("Category must be a short lowercase identifier")
    if authority is not None and authority not in ALLOWED_AUTHORITIES:
        raise ValueError("Unknown document authority")
    if document_id:
        doc = db.scalar(select(Document).where(Document.id == document_id,
                                                Document.workspace_id == workspace_id,
                                                Document.deleted_at.is_(None)))
        if not doc:
            raise ValueError("Document not found")
        if doc.kind != ALLOWED[extension]:
            raise ValueError("Replacement must use the same file type")
        latest = db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == doc.id)) or 0
        next_version = latest + 1
        if doc.status != "published":
            doc.status = "processing"
    else:
        inferred_authority = ("faq" if "faq" in Path(filename).stem.casefold()
                              else "product_manual" if "manual" in Path(filename).stem.casefold()
                              else "official_policy" if category in {"returns", "shipping", "warranty", "orders"}
                              else "uploaded")
        doc = Document(id=uid(), workspace_id=workspace_id, title=Path(filename).stem[:200],
                       kind=ALLOWED[extension], category=category,
                       authority=authority or inferred_authority,
                       status="processing", current_version=0)
        db.add(doc)
        next_version = 1
    digest = hashlib.sha256(raw).hexdigest()
    directory = settings.upload_root / workspace_id / doc.id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"v{next_version}{extension}"
    path.write_bytes(raw)
    version = DocumentVersion(id=uid(), document_id=doc.id, version=next_version,
                              sha256=digest, storage_path=str(path),
                              effective_from=effective_from, effective_to=effective_to)
    db.add(version)
    db.flush()
    job = IngestionJob(id=uid(), workspace_id=workspace_id, document_version_id=version.id,
                       status="pending", progress=0)
    db.add(job)
    db.commit()
    return doc, job


def invalidate_citations(db: Session, version_ids: list[str]) -> None:
    if not version_ids:
        return
    chunk_ids = set(db.scalars(select(Chunk.id).where(Chunk.document_version_id.in_(version_ids))).all())
    if not chunk_ids:
        return
    for message in db.scalars(select(Message).where(Message.citations.is_not(None))):
        filtered = [citation for citation in message.citations or []
                    if citation.get("chunk_id") not in chunk_ids]
        if len(filtered) != len(message.citations or []):
            message.citations = filtered


def activate_version(db: Session, doc: Document, version: DocumentVersion) -> None:
    switch_at = version.effective_from or now()
    old_versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
        DocumentVersion.id != version.id, DocumentVersion.published_at.is_not(None))).all()
    invalidate_citations(db, [item.id for item in old_versions])
    for old in old_versions:
        if old.effective_to is None or old.effective_to > switch_at:
            old.effective_to = switch_at
    version.effective_from = switch_at
    version.published_at = now()
    doc.status = "published"
    doc.current_version = version.version
    doc.updated_at = now()


def process_job(db: Session, job: IngestionJob) -> None:
    if job.cancel_requested or job.status == "cancelled":
        job.status = "cancelled"
        job.error = "Ingestion cancelled"
        job.lease_until = None
        pending_version = db.get(DocumentVersion, job.document_version_id)
        pending_doc = db.get(Document, pending_version.document_id) if pending_version else None
        if pending_doc and pending_doc.status == "processing":
            pending_doc.status = "draft"
        db.commit()
        return
    version = db.get(DocumentVersion, job.document_version_id)
    if not version:
        job.status = "failed"
        job.error = "Version not found"
        db.commit()
        return
    doc = db.get(Document, version.document_id)
    if not doc or doc.workspace_id != job.workspace_id or doc.deleted_at:
        job.status = "failed"
        job.error = "Document scope mismatch"
        db.commit()
        return
    job.status = "running"
    job.attempts += 1
    job.lease_until = now() + timedelta(minutes=5)
    job.progress = 5
    db.commit()
    try:
        db.refresh(job, attribute_names=["cancel_requested"])
        if job.cancel_requested:
            raise ValueError("Ingestion cancelled")
        raw = Path(version.storage_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != version.sha256:
            raise ValueError("Stored file hash mismatch")
        sections = extract_sections(doc.kind, raw)
        if not sections:
            raise ValueError("No extractable text found")
        db.query(Chunk).filter(Chunk.document_version_id == version.id).delete()
        ordinal = 0
        for section in sections:
            for part in split_source_text(section.page_content):
                db.add(Chunk(id=uid(), workspace_id=job.workspace_id,
                             document_version_id=version.id,
                             section=str(section.metadata["section"])[:200],
                             page=section.metadata["page"], ordinal=ordinal,
                             content=part, search_text=" ".join(tokens(part)),
                             embedding=embedding(part)))
                ordinal += 1
            db.refresh(job, attribute_names=["cancel_requested"])
            if job.cancel_requested:
                raise ValueError("Ingestion cancelled")
        db.flush()
        db.refresh(job, attribute_names=["cancel_requested"])
        if job.cancel_requested:
            raise ValueError("Ingestion cancelled")
        job.status = "completed"
        job.progress = 100
        job.error = None
        if doc.status == "published" and doc.current_version > 0:
            activate_version(db, doc, version)
        else:
            doc.status = "draft"
            doc.current_version = version.version
            doc.updated_at = now()
        db.commit()
    except Exception as error:
        db.rollback()
        current = db.get(IngestionJob, job.id)
        if current is None:
            raise RuntimeError("Ingestion job disappeared during failure handling") from error
        current.status = "cancelled" if "cancelled" in str(error).lower() else "failed"
        current.error = str(error)[:500]
        current.lease_until = None
        current_doc = db.get(Document, version.document_id)
        if current_doc and current_doc.status == "processing":
            current_doc.status = "draft"
        db.commit()


def claim_next_job(db: Session) -> IngestionJob | None:
    cutoff = now()
    query = select(IngestionJob).where(or_(IngestionJob.status == "pending",
        and_(IngestionJob.status == "running", IngestionJob.lease_until < cutoff))).order_by(IngestionJob.created_at).limit(1)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = db.scalar(query)
    if job:
        job.status = "running"
        job.lease_until = now() + timedelta(minutes=5)
        db.commit()
    return job


def _passage(row: tuple[Chunk, DocumentVersion, Document], score: float) -> Passage:
    chunk, version, doc = row
    return Passage(chunk.id, doc.title, version.version, chunk.section, chunk.page,
                   chunk.content, score, doc.category, doc.authority,
                   version.effective_from.isoformat() if version.effective_from else None)


def retrieve(db: Session, *, workspace_id: str, question: str,
             as_of: datetime | None = None, limit: int = 6,
             strategy: str = "hybrid") -> list[Passage]:
    when = as_of or now()
    query = (select(Chunk, DocumentVersion, Document)
             .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
             .join(Document, DocumentVersion.document_id == Document.id)
             .where(Chunk.workspace_id == workspace_id, Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None), Document.status == "published",
                    DocumentVersion.published_at.is_not(None),
                    DocumentVersion.published_at <= when,
                    or_(DocumentVersion.effective_from.is_(None), DocumentVersion.effective_from <= when),
                    or_(DocumentVersion.effective_to.is_(None), DocumentVersion.effective_to > when)))
    words = set(tokens(question))
    if not words:
        return []
    if db.bind and db.bind.dialect.name == "postgresql":
        tsquery = func.plainto_tsquery("english", question)
        rank = func.ts_rank_cd(func.to_tsvector("english", Chunk.search_text), tsquery)
        distance = Chunk.embedding.cosine_distance(embedding(question))
        if strategy == "baseline":
            scored = db.execute(query.add_columns(rank).where(rank > 0).order_by(rank.desc()).limit(limit)).all()
            return [_passage((row[0], row[1], row[2]), float(row[3])) for row in scored]
        scored = db.execute(query.add_columns(rank, distance)
                            .order_by((rank * 3 - distance).desc()).limit(limit * 2)).all()
        passages = [_passage((row[0], row[1], row[2]), float(row[3]) * 3 - float(row[4])) for row in scored]
    else:
        rows = db.execute(query).all()
        passages = []
        qvec = embedding(question)
        for row in rows:
            chunk = row[0]
            content_words = set(tokens(chunk.content))
            overlap = len(words & content_words) / max(1, len(words))
            vector = sum(a * b for a, b in zip(qvec, chunk.embedding, strict=True))
            score = overlap if strategy == "baseline" else overlap * 3 + vector
            if overlap > 0 or vector > 0.1:
                passages.append(_passage(row, score))
    if strategy == "baseline":
        passages.sort(key=lambda item: item.score, reverse=True)
        return passages[:limit]
    qwords = set(tokens(question.replace("-", " ")))
    return_window_question = bool(
        qwords & {"monitor", "monitors", "display", "displays"}
        and qwords & {"day", "days", "deadline", "window", "period"}
        and qwords & {"faq", "return", "returns", "general", "overview", "source", "sources"}
    )
    compatibility_question = bool(
        qwords & {"dock", "host", "video", "usb", "vesa", "fit", "compatible", "compatibility"}
        or "displays" in qwords and qwords & {"two", "connect", "port", "ports"}
    )
    primary_category = (
        "compatibility" if compatibility_question
        else "accounts" if qwords & {"ownership", "authenticate", "authentication", "identity", "proves"}
        else "payments" if qwords & {"refunds", "payment", "payments", "billing", "receipt", "receipts"}
        and not qwords & {"return", "returns", "exchange", "eligibility"}
        else "returns" if return_window_question or qwords & {"return", "returns", "refund", "refunds", "exchange", "eligibility"}
        else "shipping" if qwords & {"shipping", "delivery", "shipment", "late", "tracking", "delay"}
        else "warranty" if "warranty" in qwords else None
    )
    workspace = db.get(Workspace, workspace_id)
    priority = workspace.policy_priority if workspace and workspace.policy_priority else [
        "official_policy", "product_manual", "faq"]
    authority_weight = {name: max(0.0, 2.5 - index) for index, name in enumerate(priority)}
    def adjusted(item: Passage) -> Passage:
        title_terms = set(tokens(item.document_title)) - {"manual", "owner", "policy", "and", "the"}
        title_match = len(qwords & title_terms) / max(1, len(title_terms))
        exact_product = (5.0 if item.authority == "product_manual"
                         and item.document_title.casefold().removesuffix(" owner manual") in question.casefold()
                         else 0.0)
        authority = authority_weight.get(item.authority, 0.0) if primary_category and item.category == primary_category else 0.0
        category = 2.0 if primary_category and item.category == primary_category else 0.0
        return replace(item, score=item.score + authority + category + title_match * 2.5 + exact_product)
    passages = [adjusted(item) for item in passages]
    passages.sort(key=lambda item: item.score, reverse=True)
    return passages[:limit]


def validate_citations(citation_ids: list[str], retrieved: list[Passage]) -> list[dict]:
    allowed = {item.chunk_id: item for item in retrieved}
    return [allowed[chunk_id].citation() for chunk_id in citation_ids if chunk_id in allowed]
