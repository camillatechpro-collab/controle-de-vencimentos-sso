"""Popula uma empresa de DEMONSTRAÇÃO com dados fictícios (para testes e apresentações).

Uso:
    python scripts/dados_demo.py
Cria (se não existir) a empresa "Empresa Demonstração" com o login:
    demo@exemplo.com.br / Demo2026senha
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from sst.domain.enums import AlvoTipo, Categoria, Perfil  # noqa: E402
from sst.domain.permissoes import UsuarioContexto  # noqa: E402
from sst.infra.db.engine import criar_tabelas, session_scope  # noqa: E402
from sst.infra.db.models import TipoControle, Usuario  # noqa: E402
from sst.logging_config import setup_logging  # noqa: E402
from sst.services.cadastro_service import (  # noqa: E402
    CargoService,
    ColaboradorService,
    EquipamentoService,
    FornecedorService,
    SetorService,
    UnidadeService,
)
from sst.services.conformidade_service import ConformidadeService  # noqa: E402
from sst.services.tenant_service import criar_tenant  # noqa: E402
from sst.services.vencimento_service import VencimentoService  # noqa: E402

from sst.demo import EMAIL, SENHA  # noqa: E402
NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elaine", "Fábio", "Gabriela", "Henrique", "Isabela",
         "João", "Karina", "Lucas", "Mariana", "Nelson", "Olívia", "Paulo", "Renata", "Sérgio",
         "Tatiane", "Vinícius"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Pereira", "Lima", "Costa", "Almeida", "Rocha"]


def gerar_cpf(rnd: random.Random) -> str:
    n = [rnd.randint(0, 9) for _ in range(9)]
    for t in (9, 10):
        s = sum(n[i] * (t + 1 - i) for i in range(t))
        n.append((s * 10) % 11 % 10)
    return "".join(map(str, n))


def main() -> int:
    setup_logging()
    criar_tabelas()
    rnd = random.Random(42)
    with session_scope() as s:
        u = s.scalars(select(Usuario).where(Usuario.email == EMAIL)).first()
        uid, tid = (u.id, u.tenant_id) if u else (None, None)
    if uid is None:
        tid = criar_tenant("Empresa Demonstração", "11222333000181", "Usuário Demo", EMAIL, SENHA)
        with session_scope() as s:
            uid = s.scalars(select(Usuario.id).where(Usuario.email == EMAIL)).one()
    else:
        print("Empresa demo já existe; somente adicionando dados.")
    ctx = UsuarioContexto(uid, tid, "Usuário Demo", EMAIL, Perfil.ADMIN)

    un = UnidadeService(ctx)
    if not un.opcoes():
        u1 = un.criar({"nome": "Matriz - São Paulo", "cidade": "São Paulo", "uf": "SP"})
        u2 = un.criar({"nome": "Filial - Campinas", "cidade": "Campinas", "uf": "SP"})
        se = SetorService(ctx)
        setores = {u1: [se.criar({"unidade_id": u1, "nome": n}) for n in ("Manutenção", "Produção")],
                   u2: [se.criar({"unidade_id": u2, "nome": n}) for n in ("Logística", "Elétrica")]}
        ca = CargoService(ctx)
        cargos = {n: ca.criar({"nome": n}) for n in ("Eletricista", "Mecânico", "Operador de Empilhadeira", "Técnico de Segurança")}
        FornecedorService(ctx).criar({"razao_social": "Clínica Ocupacional Exemplo", "tipo": "CLINICA"})

        with session_scope() as s:
            tipos = {t.nome: t for t in s.scalars(select(TipoControle).where(TipoControle.tenant_id == tid))}
        cs = ConformidadeService(ctx)
        aso = tipos["ASO Periódico"].id
        cs.definir_requisitos(cargos["Eletricista"], [aso, tipos["NR-10 Básico - Reciclagem"].id, tipos["NR-35 Trabalho em Altura - Periódico"].id])
        cs.definir_requisitos(cargos["Mecânico"], [aso, tipos["NR-12 Máquinas e Equipamentos"].id])
        cs.definir_requisitos(cargos["Operador de Empilhadeira"], [aso, tipos["NR-11 Operador de Empilhadeira"].id])
        cs.definir_requisitos(cargos["Técnico de Segurança"], [aso])

        col = ColaboradorService(ctx)
        vs = VencimentoService(ctx)
        hoje = date.today()
        for i in range(20):
            unidade = u1 if i % 2 == 0 else u2
            cargo_nome = list(cargos)[i % 4]
            cid = col.criar({
                "nome": f"{NOMES[i]} {rnd.choice(SOBRENOMES)}", "cpf": gerar_cpf(rnd),
                "matricula": f"{1000 + i}", "unidade_id": unidade, "setor_id": rnd.choice(setores[unidade]),
                "cargo_id": cargos[cargo_nome], "data_admissao": hoje - timedelta(days=rnd.randint(200, 3000)),
            })
            for tipo_id in cs.requisitos_do_cargo(cargos[cargo_nome]):
                if rnd.random() < 0.15:
                    continue  # gera pendência "sem registro"
                emissao = hoje - timedelta(days=rnd.randint(30, 760))
                t = next(t for t in tipos.values() if t.id == tipo_id)
                dados = {"tipo_controle_id": tipo_id, "colaborador_id": cid, "data_emissao": emissao,
                         "emissor": "Instituição Exemplo"}
                if t.categoria == Categoria.EXAME:
                    dados |= {"ex_tipo_aso": "PERIODICO", "ex_resultado": "APTO", "ex_medico_nome": "Dr. Exemplo"}
                if t.categoria == Categoria.TREINAMENTO:
                    dados |= {"tr_carga_horaria": t.carga_horaria_padrao or 8, "tr_modalidade": "PRESENCIAL"}
                vs.criar(dados)

        eq = EquipamentoService(ctx)
        ext_rec = tipos["Extintor - Recarga/Manutenção Nível 2"].id
        for i in range(8):
            eid = eq.criar({"unidade_id": u1 if i < 5 else u2, "descricao": f"Extintor PQS 6kg nº {i + 1}",
                            "tipo": "Extintor", "patrimonio": f"EXT-{i + 1:03d}"})
            vs.criar({"tipo_controle_id": ext_rec, "equipamento_id": eid,
                      "data_emissao": hoje - timedelta(days=rnd.randint(200, 400)), "eq_tipo_servico": "RECARGA"})
        for nome_t, alvo_un in (("PGR - Programa de Gerenciamento de Riscos (revisão)", u1),
                                ("PCMSO - Relatório Analítico", u1), ("AVCB / CLCB", u2)):
            t = tipos[nome_t]
            dados = {"tipo_controle_id": t.id, "alvo_unidade_id": alvo_un,
                     "data_emissao": hoje - timedelta(days=rnd.randint(100, 500))}
            if t.alvo_tipo == AlvoTipo.UNIDADE and t.validade_valor is None:
                dados["data_vencimento"] = hoje + timedelta(days=rnd.randint(-10, 200))
            vs.criar(dados)
        print("✔ Dados de demonstração criados.")
    print(f"Login: {EMAIL}  Senha: {SENHA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
