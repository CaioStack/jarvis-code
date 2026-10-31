"""Testes para core.undo.py — pilha compartilhada de desfazer.

A pilha e um modulo global, entao cada teste comeca com clear() para isolar
o estado entre si.
"""
from core.undo import (
    MAX_DEPTH,
    can_undo,
    clear,
    history,
    peek,
    push_undo,
    undo_last,
)


def _label(i: int) -> str:
    return f"operacao {i}"


def test_pilha_vazia_inicial():
    clear()
    assert can_undo() is False
    assert peek() == ""
    assert history() == []


def test_push_e_undo_last_desfaz_mais_recente():
    clear()
    chamadas = []

    def primeiro():
        chamadas.append("primeiro")
        return "r1"

    def segundo():
        chamadas.append("segundo")
        return "r2"

    push_undo("primeiro", primeiro)
    push_undo("segundo", segundo)

    assert can_undo() is True
    assert peek() == "segundo"
    assert history() == ["segundo", "primeiro"]  # mais recente primeiro

    resultado = undo_last()
    assert resultado.startswith("Undone: segundo")
    assert chamadas == ["segundo"]

    assert peek() == "primeiro"
    undo_last()
    assert can_undo() is False


def test_limite_dez_descarta_a_mais_antiga():
    clear()
    for i in range(MAX_DEPTH + 3):
        push_undo(_label(i), lambda i=i: f"r{i}")

    hist = history()
    assert len(hist) == MAX_DEPTH
    assert _label(0) not in hist  # a mais antiga foi descartada
    assert _label(MAX_DEPTH + 2) in hist


def test_quando_vazio_undo_last_retorna_mensagem():
    clear()
    assert "nothing to undo" in undo_last().lower()


def test_clear_esvazia_pilha():
    clear()
    push_undo("x", lambda: "r")
    assert can_undo() is True
    clear()
    assert can_undo() is False
    assert peek() == ""
    assert history() == []
