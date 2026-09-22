from remitx_api.services.contact_masking import mask_email, mask_mobile


def test_an_email_keeps_its_first_letter_and_domain():
    assert mask_email("tendai@gmail.com") == "t•••@gmail.com"


def test_a_malformed_email_is_hidden_entirely():
    assert mask_email("not-an-email") == "•••"
    assert mask_email("@gmail.com") == "•••"


def test_a_mobile_keeps_its_country_code_prefix_and_last_two_digits():
    assert mask_mobile("+263771234523") == "+2637••••••23"
    assert mask_mobile("+27821234567") == "+2782•••••67"


def test_a_short_mobile_keeps_only_its_last_two_digits():
    assert mask_mobile("+2712") == "•••12"


def test_missing_contact_stays_missing():
    assert mask_email(None) is None
    assert mask_email("") is None
    assert mask_mobile(None) is None
