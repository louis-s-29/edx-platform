"""
Signal handler for enabling/disabling self-generated certificates based on the course-pacing.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from common.djangoapps.course_modes import api as modes_api
from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.signals import ENROLLMENT_TRACK_UPDATED
from lms.djangoapps.certificates.generation_handler import (
    generate_allowlist_certificate_task,
    generate_certificate_task,
    is_on_certificate_allowlist
)
from lms.djangoapps.certificates.models import (
    CertificateAllowlist,
    CertificateGenerationCourseSetting,
    CertificateStatuses,
    GeneratedCertificate
)
from lms.djangoapps.verify_student.services import IDVerificationService
from openedx.core.djangoapps.certificates.api import auto_certificate_generation_enabled
from openedx.core.djangoapps.content.course_overviews.signals import COURSE_PACING_CHANGED
from openedx.core.djangoapps.signals.signals import (
    COURSE_GRADE_NOW_FAILED,
    COURSE_GRADE_NOW_PASSED,
    LEARNER_NOW_VERIFIED
)

log = logging.getLogger(__name__)


@receiver(COURSE_PACING_CHANGED, dispatch_uid="update_cert_settings_on_pacing_change")
def _update_cert_settings_on_pacing_change(sender, updated_course_overview, **kwargs):  # pylint: disable=unused-argument
    """
    Catches the signal that course pacing has changed and enable/disable
    the self-generated certificates according to course-pacing.
    """
    CertificateGenerationCourseSetting.set_self_generation_enabled_for_course(
        updated_course_overview.id,
        updated_course_overview.self_paced,
    )
    log.info('Certificate Generation Setting Toggled for {course_id} via pacing change'.format(
        course_id=updated_course_overview.id
    ))


@receiver(post_save, sender=CertificateAllowlist, dispatch_uid="append_certificate_allowlist")
def _listen_for_certificate_allowlist_append(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    Listen for a user being added to or modified on the allowlist
    """
    if not auto_certificate_generation_enabled():
        return

    if is_on_certificate_allowlist(instance.user, instance.course_id):
        log.info(f'User {instance.user.id} is now on the allowlist for course {instance.course_id}. Attempt will be '
                 f'made to generate an allowlist certificate.')
        return generate_allowlist_certificate_task(instance.user, instance.course_id)


@receiver(COURSE_GRADE_NOW_PASSED, dispatch_uid="new_passing_learner")
def listen_for_passing_grade(sender, user, course_id, **kwargs):  # pylint: disable=unused-argument
    """
    Listen for a signal indicating that the user has passed a course run.

    If needed, generate a certificate task.
    """
    if not auto_certificate_generation_enabled():
        return

    cert = GeneratedCertificate.certificate_for_student(user, course_id)
    if cert is not None and CertificateStatuses.is_passing_status(cert.status):
        log.info(f'The cert status is already passing for user {user.id} : {course_id}. Passing grade signal will be '
                 f'ignored.')
        return
    log.info(f'Attempt will be made to generate a course certificate for {user.id} : {course_id} as a passing grade '
             f'was received.')
    return generate_certificate_task(user, course_id)


@receiver(COURSE_GRADE_NOW_FAILED, dispatch_uid="new_failing_learner")
def _listen_for_failing_grade(sender, user, course_id, grade, **kwargs):  # pylint: disable=unused-argument
    """
    Listen for a signal indicating that the user has failed a course run.

    If needed, mark the certificate as notpassing.
    """
    if is_on_certificate_allowlist(user, course_id):
        log.info(f'User {user.id} is on the allowlist for {course_id}. The failing grade will not affect the '
                 f'certificate.')
        return

    cert = GeneratedCertificate.certificate_for_student(user, course_id)
    if cert is not None:
        if CertificateStatuses.is_passing_status(cert.status):
            enrollment_mode, __ = CourseEnrollment.enrollment_mode_for_user(user, course_id)
            cert.mark_notpassing(mode=enrollment_mode, grade=grade.percent, source='notpassing_signal')
            log.info(f'Certificate marked not passing for {user.id} : {course_id} via failing grade')


@receiver(LEARNER_NOW_VERIFIED, dispatch_uid="learner_track_changed")
def _listen_for_id_verification_status_changed(sender, user, **kwargs):  # pylint: disable=unused-argument
    """
    Listen for a signal indicating that the user's id verification status has changed.
    """
    if not auto_certificate_generation_enabled():
        return

    user_enrollments = CourseEnrollment.enrollments_for_user(user=user)
    expected_verification_status = IDVerificationService.user_status(user)
    expected_verification_status = expected_verification_status['status']

    for enrollment in user_enrollments:
        log.info(f'Attempt will be made to generate a course certificate for {user.id} : {enrollment.course_id}. Id '
                 f'verification status is {expected_verification_status}')
        generate_certificate_task(user, enrollment.course_id)


@receiver(ENROLLMENT_TRACK_UPDATED)
def _listen_for_enrollment_mode_change(sender, user, course_key, mode, **kwargs):  # pylint: disable=unused-argument
    """
    Listen for the signal indicating that a user's enrollment mode has changed.

    If possible, grant the user a course certificate. Note that we intentionally do not revoke certificates here, even
    if the user has moved to the audit track.
    """
    if modes_api.is_eligible_for_certificate(mode):
        log.info(f'Attempt will be made to generate a course certificate for {user.id} : {course_key} since the '
                 f'enrollment mode is now {mode}.')
        generate_certificate_task(user, course_key)
