from jev_zork.text import clean, is_dark, split_room, strip_intro, truncate

# Premier écran réel de Zork I sous Jericho 3.3.1 (révision 88, série 840726).
INTRO = (
    "Copyright (c) 1981, 1982, 1983 Infocom, Inc. All rights reserved.\n"
    "ZORK is a registered trademark of Infocom, Inc.\n"
    "Revision 88 / Serial number 840726\n\n"
    "West of House\n"
    "You are standing in an open field west of a white house, with a boarded front door.\n"
    "There is a small mailbox here.\n\n"
)


def test_clean_normalizes_line_endings_and_blank_runs():
    assert clean("  a  \r\n\r\n\r\n\r\nb\r c \n") == "a\n\nb\n c"


def test_strip_intro_removes_the_infocom_banner():
    assert strip_intro(INTRO) == (
        "West of House\n"
        "You are standing in an open field west of a white house, with a boarded front door.\n"
        "There is a small mailbox here."
    )


def test_strip_intro_keeps_text_without_banner():
    assert strip_intro("Taken.\n\n") == "Taken."


def test_strip_intro_of_a_banner_alone_is_empty():
    assert strip_intro("Revision 88 / Serial number 840726") == ""


def test_split_room_separates_title_and_description():
    title, description = split_room(
        "West of House\nYou are standing in an open field.\nThere is a small mailbox here.\n\n"
    )
    assert title == "West of House"
    assert description == "You are standing in an open field.\nThere is a small mailbox here."


def test_split_room_rejects_sentences_and_darkness():
    grue = "It is pitch black. You are likely to be eaten by a grue."
    assert split_room(grue) == (None, grue)
    assert split_room("Taken.") == (None, "Taken.")
    assert split_room("") == (None, "")


def test_split_room_rejects_an_overlong_first_line():
    assert split_room("A" * 60)[0] is None


def test_is_dark():
    assert is_dark("It is pitch black. You are likely to be eaten by a grue.")
    assert not is_dark("West of House")


def test_truncate_cuts_on_a_word_boundary_with_an_ellipsis():
    assert truncate("the quick brown fox jumps", 15) == "the quick…"


def test_truncate_keeps_short_text_and_flattens_whitespace():
    assert truncate("a\n  b", 10) == "a b"


def test_truncate_hard_cuts_a_single_long_word():
    assert truncate("x" * 20, 6) == "xxxxx…"
