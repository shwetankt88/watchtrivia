"""A test runner that builds the static manifest once, before anything renders.

The project uses `CompressedManifestStaticFilesStorage` in every environment,
including tests, on purpose: a hashed-filename bug that only appears with the
manifest storage should fail the test suite, not production.

The cost is that `{% static %}` raises "Missing staticfiles manifest entry"
until `collectstatic` has run, and no test does that. So it is done here, once
per run, before the first test. Plain `StaticFilesStorage` would make the
twenty template tests pass, but only by testing a storage backend that the
deployed site never uses.
"""

from django.core.management import call_command
from django.test.runner import DiscoverRunner


class StaticFilesTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        call_command("collectstatic", interactive=False, verbosity=0)
