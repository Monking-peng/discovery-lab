from enum import StrEnum


class StudyStatus(StrEnum):
    DRAFT = "DRAFT"
    SCOPED = "SCOPED"
    COLLECTING = "COLLECTING"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    ARCHIVED = "ARCHIVED"


class SourceStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class EvidenceReviewStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"


class ReviewDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"


class ClaimStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    INVALIDATED = "INVALIDATED"


class ClaimEvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUALIZES = "contextualizes"
    INSUFFICIENT_FOR = "insufficient_for"


class CounterevidenceStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    SEARCHED_NONE_FOUND = "SEARCHED_NONE_FOUND"
    FOUND = "FOUND"


class OpportunityStatus(StrEnum):
    """Lifecycle exposed by the first Opportunity vertical slice.

    A Draft is deliberately not a publication state. Later review/publish states
    require their own explicit workflow rather than overloading this enum.
    """

    DRAFT = "DRAFT"


class RetrievalPurpose(StrEnum):
    """Declared intent for an immutable evidence retrieval manifest."""

    SUPPORT = "support"
    COUNTEREVIDENCE = "counterevidence"
    EXPLORE = "explore"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStepStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
