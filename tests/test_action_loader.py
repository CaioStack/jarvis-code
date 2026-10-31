"""Testes para core.action_loader.py — validacao, metadados e normalizacao de nomes."""
from core.action_loader import (
    _BEHAVIORS,
    _SCHEDULING,
    META_KEYS,
    _opt_text,
    _opt_tier,
    _opt_upper,
    strip_meta,
)


def test_strip_meta_remove_apenas_chaves_meta():
    decls = [
        {"name": "a", "tier": "core", "brief": "x"},
        {"name": "b", "description": "ok"},
        "nao-e-um-dict",
        {"name": "c"},
    ]
    out = strip_meta(decls)
    assert out[0] == {"name": "a"}
    assert out[1] == {"name": "b", "description": "ok"}
    assert out[2] == "nao-e-um-dict"
    assert out[3] == {"name": "c"}


def test_strip_meta_nao_altera_entrada_sem_meta():
    decl = {"name": "z", "description": "desc"}
    assert strip_meta([decl]) == [decl]


def test_opt_upper_valida_contra_lista_permitida():
    assert _opt_upper("blocking", _BEHAVIORS) == "BLOCKING"
    assert _opt_upper("non_blocking", _BEHAVIORS) == "NON_BLOCKING"
    assert _opt_upper("qualquercoisa", _BEHAVIORS) is None
    assert _opt_upper("", _BEHAVIORS) is None
    assert _opt_upper(None, _BEHAVIORS) is None


def test_opt_scheduling():
    assert _opt_upper("when_idle", _SCHEDULING) == "WHEN_IDLE"
    assert _opt_upper("invalido", _SCHEDULING) is None


def test_opt_tier_aceita_core_e_extra():
    assert _opt_tier("core") == "core"
    assert _opt_tier("extra") == "extra"
    assert _opt_tier("qualquercoisa") is None
    assert _opt_tier("") is None


def test_opt_texto():
    assert _opt_text("  oi  ") == "oi"
    assert _opt_text("") is None
    assert _opt_text(None) is None


def test_meta_keys_contem_tier_e_brief():
    assert META_KEYS == ("tier", "brief")
