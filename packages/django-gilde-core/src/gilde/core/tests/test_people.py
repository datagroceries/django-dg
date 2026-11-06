from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from gilde.core import areas, people
from gilde.core.people import People
from gilde.core.tests import person

# An area for the tests, with a permission every project has.
NOTES = areas.Area(scope='notes', label='Notes', permission='auth.view_group', instructions='Notes.')


class CustomerPeople(People):
    """A project whose customers use the notes, known by a nickname."""

    def may_use(self, user, area):
        return user.is_active and user.username.startswith('customer')

    def handle(self, user):
        return {'customer-1': 'Kees', 'customer-2': 'not a handle!'}.get(user.username)


@mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
class MemberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anna = person('auth.view_group', username='anna', first_name='Anna', last_name='Smit')
        cls.customer = person(username='customer-1')
        cls.other_customer = person(username='customer-2')

    def test_the_people_of_an_area_are_who_have_its_permission(self):
        team = Group.objects.create(name='Team')
        team.permissions.add(Permission.objects.get(content_type__app_label='auth', codename='view_group'))
        bert = person(username='bert', first_name='Bert')
        bert.groups.add(team)
        boss = get_user_model().objects.create_superuser(username='boss', first_name='Zoe')
        person('auth.view_group', username='gone', is_active=False)

        self.assertEqual(list(people.members('notes')), [self.anna, bert, boss])
        self.assertTrue(people.may_use(self.anna, 'notes'))
        self.assertTrue(people.may_use(boss, 'notes'))
        self.assertFalse(people.may_use(self.customer, 'notes'))
        self.assertEqual(areas.scopes_for(self.anna), ['notes'])

    @override_settings(GILDE_PEOPLE='gilde.core.tests.test_people.CustomerPeople')
    def test_the_host_project_says_who_may_use_an_area_and_a_bad_handle_reaches_nobody(self):
        self.assertEqual(set(people.members('notes')), {self.customer, self.other_customer})
        self.assertFalse(people.may_use(self.anna, 'notes'))
        self.assertEqual(people.by_handle('notes'), {'kees': self.customer})
        self.assertEqual(people.mentioned('notes', {'kees', 'anna'}), [self.customer])

    def test_a_handle_is_the_username_by_default_whatever_the_email_domain(self):
        user_model = get_user_model()
        at_one = user_model(username='anna@example.com', email='anna@example.com')
        at_another = user_model(username='anna@example.org', email='anna@example.org')

        self.assertEqual(people.handle(self.anna), 'anna')
        self.assertEqual((people.handle(at_one), people.handle(at_another)), ('anna-example.com', 'anna-example.org'))

    def test_a_name_falls_back_to_the_username_and_an_email_may_be_missing(self):
        self.assertEqual((people.name(self.anna), people.short_name(self.anna)), ('Anna Smit', 'Anna'))
        self.assertEqual((people.name(self.customer), people.short_name(self.customer)), ('customer-1', 'customer-1'))
        self.assertIsNone(people.email(self.customer))


@mock.patch.dict(areas.AREAS, {'notes': NOTES}, clear=True)
class MayUseRequiredTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.view = people.may_use_required('notes')(lambda request: HttpResponse('in'))
        cls.member = person('auth.view_group', username='anna')
        cls.outsider = person(username='bert')

    def get(self, user):
        request = RequestFactory().get('/notes/')
        request.user = user
        return self.view(request)

    def test_someone_who_may_use_the_area_gets_in(self):
        self.assertEqual(self.get(self.member).content, b'in')

    def test_someone_not_signed_in_is_sent_to_sign_in(self):
        response = self.get(AnonymousUser())

        self.assertEqual(response.status_code, 302)
        self.assertIn('next=/notes/', response['Location'])

    def test_someone_signed_in_who_may_not_is_refused(self):
        with self.assertRaises(PermissionDenied):
            self.get(self.outsider)
