"""prepare.py leans on the backend's names; a rename should fail here first."""

from datetime import date

from remitx_api.models.orm.permission import PermissionCode


def test_it_imports_against_the_current_backend():
    import prepare

    assert callable(prepare.main)


def test_its_admin_read_permissions_are_real_permission_codes():
    import prepare

    assert prepare.ADMIN_READ_PERMISSIONS <= {code.value for code in PermissionCode}


def test_the_rates_it_stores_cover_every_pair_a_quote_can_ask_for():
    """Identity pairs included: a ZAR -> ZAR send still prices a fiat rate."""
    from remitx_api.services.exchange_rate_service import SUPPORTED_CURRENCIES
    from remitx_seeder.rates import HistoricalRateProvider

    today = date.today()
    provider = HistoricalRateProvider(seed=0, start=today, end=today)
    for base in SUPPORTED_CURRENCIES:
        for quote in SUPPORTED_CURRENCIES:
            assert provider.get_rate(base, quote) > 0
