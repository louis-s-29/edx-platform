"""
API tests for the openedx certificates app
"""
from contextlib import contextmanager
from datetime import datetime

import ddt
import pytz
from django.test import TestCase
from unittest.mock import patch
from edx_toggles.toggles import LegacyWaffleSwitch
from edx_toggles.toggles.testutils import override_waffle_switch

from common.djangoapps.course_modes.models import CourseMode
from common.djangoapps.student.tests.factories import CourseEnrollmentFactory, UserFactory
from openedx.core.djangoapps.certificates import api
from openedx.core.djangoapps.certificates.config import waffle as certs_waffle
from openedx.core.djangoapps.content.course_overviews.tests.factories import CourseOverviewFactory
from xmodule.data import CertificatesDisplayBehaviors
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase


BETA_TESTER_METHOD = 'openedx.core.djangoapps.certificates.api.access.is_beta_tester'
CERTS_VIEWABLE_METHOD = 'openedx.core.djangoapps.certificates.api.certs_api.certificates_viewable_for_course'
PASSED_OR_ALLOWLISTED_METHOD = 'openedx.core.djangoapps.certificates.api._has_passed_or_is_allowlisted'


# TODO: Copied from lms.djangoapps.certificates.models,
# to be resolved per https://openedx.atlassian.net/browse/EDUCATOR-1318
class CertificateStatuses:
    """
    Enum for certificate statuses
    """
    deleted = 'deleted'
    deleting = 'deleting'
    downloadable = 'downloadable'
    error = 'error'
    generating = 'generating'
    notpassing = 'notpassing'
    restricted = 'restricted'
    unavailable = 'unavailable'
    auditing = 'auditing'
    audit_passing = 'audit_passing'
    audit_notpassing = 'audit_notpassing'
    unverified = 'unverified'
    invalidated = 'invalidated'
    requesting = 'requesting'

    ALL_STATUSES = (
        deleted, deleting, downloadable, error, generating, notpassing, restricted, unavailable, auditing,
        audit_passing, audit_notpassing, unverified, invalidated, requesting
    )


class MockGeneratedCertificate:
    """
    We can't import GeneratedCertificate from LMS here, so we roll
    our own minimal Certificate model for testing.
    """
    def __init__(self, user=None, course_id=None, mode=None, status=None):
        self.user = user
        self.course_id = course_id
        self.mode = mode
        self.status = status
        self.created_date = datetime.now(pytz.UTC)
        self.modified_date = datetime.now(pytz.UTC)

    def is_valid(self):
        """
        Return True if certificate is valid else return False.
        """
        return self.status == CertificateStatuses.downloadable


@contextmanager
def configure_waffle_namespace(feature_enabled):
    """
    Context manager to configure the certs flags
    """
    namespace = certs_waffle.waffle()
    auto_certificate_generation_switch = LegacyWaffleSwitch(namespace, certs_waffle.AUTO_CERTIFICATE_GENERATION)  # pylint: disable=toggle-missing-annotation
    with override_waffle_switch(auto_certificate_generation_switch, active=feature_enabled):
        yield


@ddt.ddt
class CertificatesApiTestCase(TestCase):
    """
    API tests
    """
    def setUp(self):
        super().setUp()
        self.course = CourseOverviewFactory.create(
            start=datetime(2017, 1, 1, tzinfo=pytz.UTC),
            end=datetime(2017, 1, 31, tzinfo=pytz.UTC),
            certificate_available_date=None
        )
        self.user = UserFactory.create()
        self.enrollment = CourseEnrollmentFactory(
            user=self.user,
            course_id=self.course.id,
            is_active=True,
            mode='audit',
        )
        self.certificate = MockGeneratedCertificate(
            user=self.user,
            course_id=self.course.id
        )

    @ddt.data(True, False)
    def test_auto_certificate_generation_enabled(self, feature_enabled):
        with configure_waffle_namespace(feature_enabled):
            assert feature_enabled == api.auto_certificate_generation_enabled()

    @ddt.data(
        (True, True, False),  # feature enabled and self-paced should return False
        (True, False, True),  # feature enabled and instructor-paced should return True
        (False, True, False),  # feature not enabled and self-paced should return False
        (False, False, False),  # feature not enabled and instructor-paced should return False
    )
    @ddt.unpack
    def test_can_show_certificate_available_date_field(
            self, feature_enabled, is_self_paced, expected_value
    ):
        self.course.self_paced = is_self_paced
        with configure_waffle_namespace(feature_enabled):
            assert expected_value == api.can_show_certificate_available_date_field(self.course)

    @ddt.data(
        (True, True, False),  # feature enabled and self-paced should return False
        (True, False, True),  # feature enabled and instructor-paced should return True
        (False, True, False),  # feature not enabled and self-paced should return False
        (False, False, False),  # feature not enabled and instructor-paced should return False
    )
    @ddt.unpack
    def test_available_vs_display_date(
            self, feature_enabled, is_self_paced, uses_avail_date
    ):
        self.course.self_paced = is_self_paced
        with configure_waffle_namespace(feature_enabled):

            # With no available_date set, both return modified_date
            assert self.certificate.modified_date == api.available_date_for_certificate(self.course, self.certificate)
            assert self.certificate.modified_date == api.display_date_for_certificate(self.course, self.certificate)

            # With an available date set in the past, both return the available date (if configured)
            self.course.certificate_available_date = datetime(2017, 2, 1, tzinfo=pytz.UTC)
            self.course.certificates_display_behavior = CertificatesDisplayBehaviors.END_WITH_DATE
            maybe_avail = self.course.certificate_available_date if uses_avail_date else self.certificate.modified_date
            assert maybe_avail == api.available_date_for_certificate(self.course, self.certificate)
            assert maybe_avail == api.display_date_for_certificate(self.course, self.certificate)

            # With a future available date, they each return a different date
            self.course.certificate_available_date = datetime.max.replace(tzinfo=pytz.UTC)
            maybe_avail = self.course.certificate_available_date if uses_avail_date else self.certificate.modified_date
            assert maybe_avail == api.available_date_for_certificate(self.course, self.certificate)
            assert self.certificate.modified_date == api.display_date_for_certificate(self.course, self.certificate)


@ddt.ddt
class CertificatesMessagingTestCase(ModuleStoreTestCase):
    """
    API tests for certificate messaging
    """
    def setUp(self):
        super().setUp()
        self.course = CourseOverviewFactory.create()
        self.course_run_key = self.course.id
        self.user = UserFactory.create()
        self.enrollment = CourseEnrollmentFactory(
            user=self.user,
            course_id=self.course_run_key,
            is_active=True,
            mode=CourseMode.VERIFIED,
        )

    def test_beta_tester(self):
        grade = None
        certs_enabled = True

        with patch(PASSED_OR_ALLOWLISTED_METHOD, return_value=True):
            with patch(CERTS_VIEWABLE_METHOD, return_value=True):
                with patch(BETA_TESTER_METHOD, return_value=False):
                    assert api.can_show_certificate_message(self.course, self.user, grade, certs_enabled)

                with patch(BETA_TESTER_METHOD, return_value=True):
                    assert not api.can_show_certificate_message(self.course, self.user, grade, certs_enabled)
