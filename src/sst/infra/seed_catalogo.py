"""Catálogo inicial sugerido de tipos de controle.

IMPORTANTE: são sugestões de partida. Periodicidades podem variar conforme
PGR/PCMSO, grau de risco, legislação estadual (ex.: brigada/AVCB) e normas
técnicas. O cliente deve revisar e ajustar no menu "Tipos de controle".
"""

from __future__ import annotations

from sst.domain.enums import AlvoTipo as A
from sst.domain.enums import Categoria as C
from sst.domain.enums import ValidadeUnidade as V

# (categoria, nome, norma, alvo, validade_valor, validade_unidade, antecedencia, exige_anexo, carga_h)
CATALOGO_PADRAO: list[tuple] = [
    (C.TREINAMENTO, "NR-35 Trabalho em Altura - Periódico", "NR-35", A.COLABORADOR, 24, V.MESES, 60, True, 8),
    (C.TREINAMENTO, "NR-10 Básico - Reciclagem", "NR-10", A.COLABORADOR, 24, V.MESES, 60, True, 20),
    (C.TREINAMENTO, "NR-10 SEP - Reciclagem", "NR-10", A.COLABORADOR, 24, V.MESES, 60, True, 20),
    (C.TREINAMENTO, "NR-33 Espaço Confinado - Trabalhador/Vigia", "NR-33", A.COLABORADOR, 12, V.MESES, 45, True, 8),
    (C.TREINAMENTO, "NR-33 Espaço Confinado - Supervisor", "NR-33", A.COLABORADOR, 12, V.MESES, 45, True, 8),
    (C.TREINAMENTO, "NR-20 Inflamáveis - Intermediário (atualização)", "NR-20", A.COLABORADOR, 24, V.MESES, 60, True, 4),
    (C.TREINAMENTO, "NR-12 Máquinas e Equipamentos", "NR-12", A.COLABORADOR, 24, V.MESES, 60, True, None),
    (C.TREINAMENTO, "NR-11 Operador de Empilhadeira", "NR-11", A.COLABORADOR, 12, V.MESES, 45, True, None),
    (C.TREINAMENTO, "Brigada de Incêndio - Reciclagem", "NR-23 / IT Corpo de Bombeiros", A.COLABORADOR, 12, V.MESES, 45, True, None),
    (C.TREINAMENTO, "NR-05 CIPA - Treinamento de Membros", "NR-05", A.COLABORADOR, 12, V.MESES, 30, True, 20),
    (C.EXAME, "ASO Periódico", "NR-07 / PCMSO", A.COLABORADOR, 12, V.MESES, 30, True, None),
    (C.EXAME, "ASO Admissional", "NR-07 / PCMSO", A.COLABORADOR, None, V.SEM_VALIDADE, 0, True, None),
    (C.EXAME, "Audiometria Ocupacional", "NR-07 Anexo II", A.COLABORADOR, 12, V.MESES, 30, True, None),
    (C.EQUIPAMENTO, "Extintor - Recarga/Manutenção Nível 2", "NBR 12962", A.EQUIPAMENTO, 12, V.MESES, 30, False, None),
    (C.EQUIPAMENTO, "Extintor - Teste Hidrostático", "NBR 12962", A.EQUIPAMENTO, 5, V.ANOS, 60, False, None),
    (C.EQUIPAMENTO, "EPI - Validade do Certificado de Aprovação (CA)", "NR-06", A.EQUIPAMENTO, None, V.MANUAL, 30, False, None),
    (C.EQUIPAMENTO, "Detector de Gases - Calibração", "Fabricante", A.EQUIPAMENTO, 12, V.MESES, 30, True, None),
    (C.EQUIPAMENTO, "Vaso de Pressão - Inspeção de Segurança", "NR-13", A.EQUIPAMENTO, None, V.MANUAL, 60, True, None),
    (C.DOCUMENTO, "PGR - Programa de Gerenciamento de Riscos (revisão)", "NR-01", A.UNIDADE, 24, V.MESES, 60, True, None),
    (C.DOCUMENTO, "PCMSO - Relatório Analítico", "NR-07", A.UNIDADE, 12, V.MESES, 45, True, None),
    (C.DOCUMENTO, "AVCB / CLCB", "Corpo de Bombeiros", A.UNIDADE, None, V.MANUAL, 90, True, None),
    (C.DOCUMENTO, "Laudo de SPDA", "NBR 5419", A.UNIDADE, None, V.MANUAL, 60, True, None),
    (C.DOCUMENTO, "Laudo de Instalações Elétricas", "NR-10", A.UNIDADE, None, V.MANUAL, 60, True, None),
    (C.CONTRATO, "Contrato de Prestação de Serviços", None, A.FORNECEDOR, None, V.MANUAL, 60, True, None),
    (C.CERTIFICADO, "Registro Profissional (CREA/CRM/MTE)", None, A.COLABORADOR, None, V.MANUAL, 30, False, None),
    (C.OBRIGACAO, "Mandato da CIPA", "NR-05", A.UNIDADE, 12, V.MESES, 60, False, None),
    (C.OBRIGACAO, "SIPAT", "NR-05", A.UNIDADE, 12, V.MESES, 60, False, None),
]
