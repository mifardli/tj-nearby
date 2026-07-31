from tj_nearby.menubar import authorization_blocks_automatic_polling


def test_not_determined_does_not_block_polling():
    assert not authorization_blocks_automatic_polling("not-determined")


def test_denied_and_restricted_block_polling():
    assert authorization_blocks_automatic_polling("denied")
    assert authorization_blocks_automatic_polling("restricted")


def test_authorized_does_not_block_polling():
    assert not authorization_blocks_automatic_polling("authorized-when-in-use")
