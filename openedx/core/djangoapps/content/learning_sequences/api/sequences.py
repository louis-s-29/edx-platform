"""
All business logic related to fetching generic Learning Sequences information.
By 'generic', we mean context-agnostic; the data returned by these functions
should not be specific to Courses, Libraries, Pathways, or any other context
in which Learning Sequences can exist.

Do not import from this module directly.
Use openedx.core.djangoapps.content.learning_sequences.api -- that
__init__.py imports from here, and is a more stable place to import from.
"""
from opaque_keys.edx.keys import UsageKey

from ..data import LearningSequenceData
from ..models import LearningSequence


def get_learning_sequence(sequence_key: UsageKey) -> LearningSequenceData:
    """
    Load generic data for a learning sequence given its usage key.
    """
    try:
        sequence = LearningSequence.objects.get(usage_key=sequence_key)
    except:
        raise LearningSequenceData.DoesNotExist(   # pylint: disable=raise-missing-from
            f"could not load LearningSequenceData for usage key {sequence_key}"
        )
    return _make_sequence_data(sequence)


def get_learning_sequence_by_hash(sequence_key_hash: str) -> LearningSequenceData:
    """
    Load a generic data for a learning sequence given the hash of its usage key.
    """
    try:
        sequence = LearningSequence.objects.get(usage_key_hash=sequence_key_hash)
    except:
        raise LearningSequenceData.DoesNotExist(   # pylint: disable=raise-missing-from
            f"could not load LearningSequenceData for usage key hash {sequence_key_hash}"
        )
    return _make_sequence_data(sequence)


def _make_sequence_data(sequence: LearningSequence) -> LearningSequenceData:
    """
    Build a LearningSequenceData instance from a LearningSequence model instance.
    """
    return LearningSequenceData(
        usage_key=sequence.usage_key,
        usage_key_hash=sequence.usage_key_hash,
        title=sequence.title,
    )
