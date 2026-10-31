"""Testes para providers/schema.py — conversao, orcamento e compactacao de declaracoes de ferramentas."""
from providers.schema import (
    CORE_TOOLS,
    budget,
    compact,
    payload_size,
    to_anthropic,
    to_gemini,
    to_openai,
)

_DECL = {
    "name": "test_tool",
    "description": "Uma ferramenta de teste com descricao longa.",
    "parameters": {"type": "OBJECT", "properties": {"x": {"type": "STRING"}}},
}


def test_to_openai_converte_tipos_para_minusculo():
    decls = [dict(_DECL, parameters={"type": "OBJECT", "properties": {}})]
    out = to_openai(decls)
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "test_tool"
    assert out[0]["function"]["parameters"]["type"] == "object"


def test_to_anthropic_usa_input_schema():
    out = to_anthropic([_DECL])
    assert out[0]["name"] == "test_tool"
    assert "input_schema" in out[0]
    assert out[0]["input_schema"]["type"] == "object"


def test_to_gemini_identidade():
    assert to_gemini([_DECL]) == [_DECL]


def test_budget_sem_limites_retorna_inalterado():
    decls = [_DECL, dict(_DECL, name="outra")]
    assert budget(decls) == decls


def test_budget_limite_por_quantidade():
    decls = [dict(_DECL, name=f"t{i}") for i in range(5)]
    kept = budget(decls, max_tools=2)
    assert len(kept) == 2


def test_budget_limite_por_caracteres():
    decls = [dict(_DECL, name=f"t{i}") for i in range(5)]
    kept = budget(decls, max_chars=50)
    assert len(kept) < len(decls)


def test_compact_troca_descricao_por_brief():
    decl = dict(_DECL, brief="desc curta")
    slim = compact(decl)
    assert slim["description"] == "desc curta"
    assert "brief" not in slim
    # o original nao e alterado
    assert _DECL["description"] == "Uma ferramenta de teste com descricao longa."


def test_compact_sem_brief_deixa_inalterado():
    assert compact(_DECL) == _DECL


def test_payload_size_contagem_positiva():
    assert payload_size([_DECL]) > 0


def test_core_tools_nao_vazio():
    assert "open_app" in CORE_TOOLS
    assert "undo" in CORE_TOOLS
