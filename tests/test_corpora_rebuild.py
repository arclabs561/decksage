"""Rebuilt corpus rules: deck identity and narrowly-guarded name resolution."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/training/{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rebuild = load_module("corpora_rebuild")


def index(*names):
    return rebuild.NameIndex(names)


def test_pipeline_key_is_strip_only():
    # The pipeline does not case-fold or strip punctuation: measured, not assumed.
    assert rebuild.pipeline_key("  Lightning Bolt ") == "Lightning Bolt"
    assert rebuild.pipeline_key("lightning bolt") == "lightning bolt"


def test_deck_signature_is_order_insensitive_and_count_sensitive():
    a = [("Island", 7), ("Opt", 4)]
    b = [("Opt", 4), ("Island", 7)]
    c = [("Opt", 3), ("Island", 8)]
    assert rebuild.deck_signature(a) == rebuild.deck_signature(b)
    assert rebuild.deck_signature(a) != rebuild.deck_signature(c)


def test_deck_signature_ignores_zero_counts():
    assert rebuild.deck_signature([("Opt", 4), ("Bad", 0)]) == rebuild.deck_signature([("Opt", 4)])


def test_exact_match_wins_and_is_never_rewritten():
    idx = index("Wear // Tear", "Wear")
    assert idx.resolve("Wear") == ("Wear", "exact")
    assert idx.resolve("Wear // Tear") == ("Wear // Tear", "exact")


def test_slash_separator_maps_to_split_name():
    idx = index("Wear // Tear", "Wear Down")
    assert idx.resolve("Wear/Tear") == ("Wear // Tear", "slash_separator")


def test_slash_separator_refuses_unknown_join():
    idx = index("Wear // Tear")
    assert idx.resolve("Wear/Apart") == (None, "unresolved")


def test_casefold_rule_maps_case_variant():
    idx = index("Lightning Bolt")
    assert idx.resolve("LIGHTNING BOLT") == ("Lightning Bolt", "casefold")


def test_accent_rule_maps_diacritic_variant():
    idx = index("Troll of Khazad-dûm", "Lórien Revealed")
    assert idx.resolve("Troll of Khazad-dum") == ("Troll of Khazad-dûm", "accent")
    assert idx.resolve("Lorien Revealed") == ("Lórien Revealed", "accent")


def test_accent_rule_refuses_ambiguous_diacritics():
    # Two metadata cards differing only by a diacritic must stay unresolved.
    idx = index("El-Hajjâj", "El-Hajjaj")
    assert idx.resolve("El Hajjaj")[0] is None


def test_face_split_maps_single_face_to_unique_split_card():
    idx = index("Cragcrown Pathway // Timbercrown Pathway", "Opt")
    assert idx.resolve("Timbercrown Pathway") == (
        "Cragcrown Pathway // Timbercrown Pathway",
        "face_split",
    )


def test_face_split_refuses_when_face_is_ambiguous():
    idx = index("A // Shared", "B // Shared")
    assert idx.resolve("Shared") == (None, "unresolved")


def test_face_split_ignores_self_pair_shell_rows():
    # card_attributes_magic_enriched.csv carries "X // X" phantom shells; they
    # must not make the genuine "X // Y" face ambiguous.
    idx = index(
        "Clearwater Pathway // Clearwater Pathway", "Clearwater Pathway // Murkwater Pathway"
    )
    assert idx.resolve("Clearwater Pathway") == (
        "Clearwater Pathway // Murkwater Pathway",
        "face_split",
    )


def test_ygo_angle_bracket_rule():
    idx = index("Maliss <Q> White Binder", "Maliss in the Mirror")
    assert idx.resolve("Maliss Q White Binder") == ("Maliss <Q> White Binder", "ygo_angle")

    # A real card whose name starts with the same prefix is never rewritten.
    idx2 = index("Maliss <Q> White Binder", "Maliss Q")
    assert idx2.resolve("Maliss Q") == ("Maliss Q", "exact")


def test_strip_quotes_rule():
    idx = index('"Infernoble Arms - Durendal"')
    assert idx.resolve("Infernoble Arms - Durendal") == (
        '"Infernoble Arms - Durendal"',
        "strip_quotes",
    )


def test_ace_suffix_rule_requires_bare_base():
    idx = index("Zephagamon")
    assert idx.resolve("Zephagamon ACE") == ("Zephagamon", "ace_suffix")
    assert idx.resolve("Unknownmon ACE") == (None, "unresolved")


def test_placeholder_ids_are_not_resolved():
    idx = index("Card_14558128")
    assert idx.resolve("Card_99999999") == (None, "unresolved")


def test_pairs_accumulate_set_and_multiset_counts():
    decks = [
        ("d1", {"cards": [{"name": "A", "count": 2}, {"name": "B", "count": 1}]}),
        ("d2", {"cards": [{"name": "A", "count": 3}, {"name": "B", "count": 4}]}),
    ]
    result = rebuild.build_pairs(decks)
    names = result["names"]
    set_counts = result["set_counts"]
    multi_counts = result["multi_counts"]
    assert len(set_counts) == 1
    (key,) = set_counts
    assert {names[key >> 32], names[key & 0xFFFFFFFF]} == {"A", "B"}
    assert set_counts[key] == 2
    assert multi_counts[key] == 2 * 1 + 3 * 4


def test_pairs_drop_unresolved_rows_when_asked():
    idx = index("A")
    decks = [
        (
            "d1",
            {
                "cards": [
                    {"name": "A", "count": 1},
                    {"name": "B", "count": 1},
                ]
            },
        )
    ]
    result = rebuild.build_pairs(decks, resolve=idx.resolve, drop_unresolved=True)
    assert result["unresolved_unique"] == 1
    assert result["dropped_rows"] == 1
    assert result["set_counts"] == {}


def test_weight_summary_histogram_is_bounded():
    summary = rebuild.weight_summary([1, 1, 2, 5, 40, 500])
    assert summary["rows"] == 6
    assert summary["max"] == 500
    assert summary["histogram"] == {"1": 2, "2-3": 1, "4-10": 1, "11-100": 1, "101+": 1}


def test_punct_fold_repairs_typographic_quotes_and_dashes():
    idx = index(
        'Gigantic "Champion" Sargas',
        "Gold Pride - Start Your Engines!",
        "Fabled Realm's Revival",
    )
    assert idx.resolve("Gigantic \u201cChampion\u201d Sargas") == (
        'Gigantic "Champion" Sargas',
        "punct_variant",
    )
    assert idx.resolve("Gold Pride \u2013 Start Your Engines!") == (
        "Gold Pride - Start Your Engines!",
        "punct_variant",
    )
    assert idx.resolve("Fabled Realm\u2019s Revival") == (
        "Fabled Realm's Revival",
        "punct_variant",
    )


def test_punct_fold_refuses_when_two_cards_share_the_fold():
    idx = index("Gold Pride \u2013 A", "Gold Pride \u2014 A")
    # Two metadata cards fold to the same key, so the hyphen spelling is
    # genuinely ambiguous and must stay unresolved.
    assert idx.resolve("Gold Pride - A") == (None, "unresolved")


def test_punct_fold_does_not_rewrite_structure():
    idx = index("Wear // Tear", "Maliss <Q> Hearts Crypter")
    # Slash and angle-bracket repairs keep their own tiers and names.
    assert idx.resolve("Wear/Tear") == ("Wear // Tear", "slash_separator")
    assert idx.resolve("Maliss Q Hearts Crypter") == (
        "Maliss <Q> Hearts Crypter",
        "ygo_angle",
    )
