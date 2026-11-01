"""Certificados de Aforro (esquema v7): subscrições e simulação do valor no vencimento.

Regras da série E (Portaria n.º 329-A/2017, confirmadas a 01/11/2026):
- Taxa base mensal = Euribor a 3 meses (média dos 10 dias úteis anteriores) + 1 p.p., arredondada à 3.ª casa
  decimal, entre 0 % e 3,5 %. A taxa de cada trimestre é a taxa base em vigor no início do trimestre + o prémio
  de permanência: 0,5 p.p. do 2.º ao 5.º ano e 1 p.p. do 6.º ao 10.º ano.
- Os juros vencem de 3 em 3 meses, no dia da subscrição (se esse dia não existir no mês, no dia 1 do mês seguinte),
  e são capitalizados líquidos de IRS (28 %, retido na fonte). Prazo de 10 anos: no 10.º aniversário reembolsa-se
  o capital e os juros capitalizados, sem mais imposto.

O valor final depende da Euribor futura, por isso não há previsão única: simulam-se cenários com a taxa base
constante até ao fim. O mínimo (taxa base 0 %) e o máximo (3,5 %) são limites das regras; o do meio usa a taxa
base atual escrita pelo dono.

Por confirmar (a Portaria não o diz): o juro do trimestre calcula-se como taxa anual ÷ 4 e o valor unitário
arredonda às 5 casas em cada vencimento. Confirma-se comparando o valor unitário previsto para o próximo
vencimento com o do extrato seguinte. O arredondamento pesa menos de 1 € no total.

A simulação parte do valor unitário do último extrato (o histórico de taxas não é preciso) e conta como já
capitalizados os vencimentos até à data desse extrato, inclusive.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from app import calc

ESCALA_VU = 100_000  # valor unitário com 5 casas decimais
ESCALA_TAXA = 1_000  # taxas em milésimas de ponto percentual: 2,951 % -> 2951
IRS = Fraction(28, 100)
LIMITE_UNIDADES = 250_000  # máximo por conta (Portaria)
LIMITE_VU = 10 * ESCALA_VU  # 10 € por unidade: muito acima de qualquer valor possível

CHAVE_TAXA = "aforro_{serie}_taxa_base"  # tabela configuracao, em milésimas de ponto percentual
CHAVE_DATA = "aforro_{serie}_taxa_base_data"  # dia em que foi escrita, como AAAAMMDD


@dataclass(frozen=True)
class Serie:
    nome: str
    prazo_anos: int
    teto_taxa_base: int  # milésimas de p.p.
    premios: tuple[tuple[int, int, int], ...]  # (do ano, ao ano, prémio em milésimas de p.p.)

    def premio(self, ano: int) -> int:
        return next((p for de, ate, p in self.premios if de <= ano <= ate), 0)


SERIES = {
    "E": Serie("Série E", 10, 3_500, ((2, 5, 500), (6, 10, 1_000))),
}


@dataclass(frozen=True)
class Subscricao:
    id: int
    plataforma_id: int
    plataforma: str
    serie: str
    data_subscricao: date
    unidades: int
    valor_unitario: int  # centésimas de milésima de euro
    data_valor: date

    @property
    def valor_cent(self) -> int:
        return _cent(self.unidades * Fraction(self.valor_unitario, ESCALA_VU))


@dataclass(frozen=True)
class Cenario:
    codigo: str
    rotulo: str
    taxa_base: int  # milésimas de p.p.


@dataclass(frozen=True)
class Projecao:
    subscricao: Subscricao
    vencimento: date
    vencida: bool
    proximo_vencimento: date | None
    trimestres_em_falta: int
    valor_final_cent: dict[str, int]  # código do cenário -> valor no vencimento
    proximo_vu: dict[str, int]  # código do cenário -> valor unitário previsto no próximo vencimento


@dataclass(frozen=True)
class Resumo:
    projecoes: list[Projecao]
    cenarios: list[Cenario]
    taxa_atual: int | None
    taxa_atual_data: date | None
    valor_hoje_cent: int
    total_final_cent: dict[str, int]


# --- Datas e cálculo ----------------------------------------------------------------------------------------

def somar_meses(d: date, meses: int) -> date:
    """Mesmo dia `meses` depois; se o dia não existir nesse mês, o dia 1 do mês seguinte (regra do IGCP)."""
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano += d.year
    try:
        return date(ano, mes + 1, d.day)
    except ValueError:
        ano2, mes2 = divmod(mes + 1, 12)
        return date(ano + ano2, mes2 + 1, 1)


def vencimento_juros(data_subscricao: date, k: int) -> date:
    """Data do k-ésimo vencimento de juros (k = 1 é 3 meses depois da subscrição)."""
    return somar_meses(data_subscricao, 3 * k)


def _arredondar(x: Fraction, escala: int) -> int:
    """Fração -> inteiro na escala dada, meio para cima (só valores positivos)."""
    return int(x * escala + Fraction(1, 2))


def _cent(euros: Fraction) -> int:
    return _arredondar(euros, 100)


def taxa_do_trimestre(serie: Serie, k: int, taxa_base: int) -> int:
    """Taxa anual bruta (milésimas de p.p.) do trimestre que termina no vencimento k."""
    ano = (k - 1) // 4 + 1
    return min(max(taxa_base, 0), serie.teto_taxa_base) + serie.premio(ano)


def capitalizar(serie: Serie, vu: int, k: int, taxa_base: int) -> int:
    """Valor unitário depois do vencimento k: juro trimestral = taxa ÷ 4, líquido de IRS, arredondado a 5 casas."""
    taxa = Fraction(taxa_do_trimestre(serie, k, taxa_base), ESCALA_TAXA * 100)
    v = Fraction(vu, ESCALA_VU)
    return _arredondar(v + v * taxa / 4 * (1 - IRS), ESCALA_VU)


def projetar(s: Subscricao, cenarios: list[Cenario]) -> Projecao:
    serie = SERIES[s.serie]
    total = 4 * serie.prazo_anos
    feitos = sum(1 for k in range(1, total + 1) if vencimento_juros(s.data_subscricao, k) <= s.data_valor)
    finais: dict[str, int] = {}
    proximos: dict[str, int] = {}
    for c in cenarios:
        vu = s.valor_unitario
        for k in range(feitos + 1, total + 1):
            vu = capitalizar(serie, vu, k, c.taxa_base)
            if k == feitos + 1:
                proximos[c.codigo] = vu
        finais[c.codigo] = _cent(s.unidades * Fraction(vu, ESCALA_VU))
    return Projecao(
        subscricao=s,
        vencimento=vencimento_juros(s.data_subscricao, total),
        vencida=feitos >= total,
        proximo_vencimento=vencimento_juros(s.data_subscricao, feitos + 1) if feitos < total else None,
        trimestres_em_falta=total - feitos,
        valor_final_cent=finais,
        proximo_vu=proximos,
    )


def cenarios(serie: Serie, taxa_atual: int | None) -> list[Cenario]:
    lista = [Cenario("minimo", "Mínimo (taxa base 0 %)", 0)]
    if taxa_atual is not None:
        lista.append(Cenario("atual", "Com a taxa base atual", min(taxa_atual, serie.teto_taxa_base)))
    lista.append(Cenario("maximo", f"Máximo (taxa base {taxa_para_texto(serie.teto_taxa_base)} %)",
                         serie.teto_taxa_base))
    return lista


# --- Texto <-> inteiros -------------------------------------------------------------------------------------

def _decimal_exato(texto: str, escala: int, casas: int, o_que: str) -> int:
    valor = calc.texto_para_decimal(texto)
    inteiro = valor * escala
    if inteiro != inteiro.to_integral_value():
        raise ValueError(f"{o_que} tem no máximo {casas} casas decimais")
    return int(inteiro)


def vu_de_texto(texto: str) -> int:
    """'1,08734' -> 108734. Tem de ser pelo menos 1 (o capital é garantido)."""
    vu = _decimal_exato(texto, ESCALA_VU, 5, "O valor unitário")
    if vu < ESCALA_VU:
        raise ValueError("O valor unitário não pode ser menor que 1 (o capital é garantido)")
    if vu > LIMITE_VU:
        raise ValueError(f"Valor unitário fora do intervalo aceite: {texto!r}")
    return vu


def vu_para_texto(vu: int) -> str:
    inteiro, resto = divmod(vu, ESCALA_VU)
    return f"{inteiro},{resto:05d}"


def taxa_de_texto(texto: str, serie: Serie) -> int:
    """'2,951' -> 2951. Entre 0 e o teto da série (a taxa base publicada já vem limitada)."""
    taxa = _decimal_exato(texto, ESCALA_TAXA, 3, "A taxa base")
    if not 0 <= taxa <= serie.teto_taxa_base:
        raise ValueError(f"A taxa base da {serie.nome} fica entre 0 e {taxa_para_texto(serie.teto_taxa_base)} %")
    return taxa


def taxa_para_texto(taxa: int) -> str:
    inteiro, resto = divmod(taxa, ESCALA_TAXA)
    decimais = f"{resto:03d}".rstrip("0")
    return f"{inteiro},{decimais}" if decimais else str(inteiro)


def unidades_de_texto(texto: str) -> int:
    t = (texto or "").strip().replace(".", "").replace(" ", "").replace(" ", "")
    if not t.isdigit():
        raise ValueError("As unidades são um número inteiro (ex.: 2500)")
    n = int(t)
    if not 1 <= n <= LIMITE_UNIDADES:
        raise ValueError(f"As unidades ficam entre 1 e {LIMITE_UNIDADES:,}".replace(",", "."))
    return n


def data_de_texto(texto: str, o_que: str) -> date:
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        raise ValueError(f"Indica {o_que} (dia/mês/ano)") from None


# --- Base de dados ------------------------------------------------------------------------------------------

def listar(conn: sqlite3.Connection) -> list[Subscricao]:
    sql = """SELECT s.*, p.nome AS plataforma FROM subscricoes_aforro s JOIN plataformas p ON p.id = s.plataforma_id
             ORDER BY s.data_subscricao, s.id"""
    return [
        Subscricao(r["id"], r["plataforma_id"], r["plataforma"], r["serie"], date.fromisoformat(r["data_subscricao"]),
                   r["unidades"], r["valor_unitario"], date.fromisoformat(r["data_valor"]))
        for r in conn.execute(sql)
    ]


def obter(conn: sqlite3.Connection, subscricao_id: int) -> Subscricao | None:
    return next((s for s in listar(conn) if s.id == subscricao_id), None)


@dataclass(frozen=True)
class Dados:
    plataforma_id: int
    serie: str
    data_subscricao: date
    unidades: int
    valor_unitario: int
    data_valor: date


def validar(conn: sqlite3.Connection, form: dict[str, str], hoje: date) -> tuple[Dados | None, dict[str, str]]:
    """Textos do formulário -> (dados, erros por campo)."""
    erros: dict[str, str] = {}
    try:
        plataforma_id = int(form.get("plataforma_id") or 0)
    except ValueError:
        plataforma_id = 0
    if conn.execute("SELECT 1 FROM plataformas WHERE id = ?", (plataforma_id,)).fetchone() is None:
        erros["plataforma_id"] = "Escolhe a plataforma"
    serie = (form.get("serie") or "").strip().upper()
    if serie not in SERIES:
        erros["serie"] = "Série não suportada (por agora só a E)"
    valores = {}
    for campo, funcao in (
        ("data_subscricao", lambda t: data_de_texto(t, "a data de subscrição")),
        ("unidades", unidades_de_texto),
        ("valor_unitario", vu_de_texto),
        ("data_valor", lambda t: data_de_texto(t, "a data do extrato")),
    ):
        try:
            valores[campo] = funcao(form.get(campo, ""))
        except ValueError as exc:
            erros[campo] = str(exc)
    if "data_subscricao" in valores and valores["data_subscricao"] > hoje:
        erros["data_subscricao"] = "A data de subscrição não pode ser futura"
    if "data_valor" in valores:
        if valores["data_valor"] > hoje:
            erros["data_valor"] = "A data do extrato não pode ser futura"
        elif "data_subscricao" in valores and valores["data_valor"] < valores["data_subscricao"]:
            erros["data_valor"] = "O extrato não pode ser anterior à subscrição"
    if erros:
        return None, erros
    return Dados(plataforma_id, serie, valores["data_subscricao"], valores["unidades"], valores["valor_unitario"],
                 valores["data_valor"]), {}


def _parametros(d: Dados) -> tuple:
    return (d.plataforma_id, d.serie, d.data_subscricao.isoformat(), d.unidades, d.valor_unitario,
            d.data_valor.isoformat())


def criar(conn: sqlite3.Connection, d: Dados) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO subscricoes_aforro (plataforma_id, serie, data_subscricao, unidades, valor_unitario, data_valor)
               VALUES (?, ?, ?, ?, ?, ?)""", _parametros(d))
    return cur.lastrowid


def editar(conn: sqlite3.Connection, subscricao_id: int, d: Dados) -> None:
    with conn:
        if conn.execute(
            """UPDATE subscricoes_aforro SET plataforma_id = ?, serie = ?, data_subscricao = ?, unidades = ?,
               valor_unitario = ?, data_valor = ? WHERE id = ?""", _parametros(d) + (subscricao_id,)
        ).rowcount == 0:
            raise LookupError("Subscrição inexistente")


def apagar(conn: sqlite3.Connection, subscricao_id: int) -> None:
    with conn:
        if conn.execute("DELETE FROM subscricoes_aforro WHERE id = ?", (subscricao_id,)).rowcount == 0:
            raise LookupError("Subscrição inexistente")


def obter_taxa(conn: sqlite3.Connection, serie: str = "E") -> tuple[int | None, date | None]:
    linhas = {
        r["chave"]: r["valor"]
        for r in conn.execute("SELECT chave, valor FROM configuracao WHERE chave IN (?, ?)",
                              (CHAVE_TAXA.format(serie=serie.lower()), CHAVE_DATA.format(serie=serie.lower())))
    }
    taxa = linhas.get(CHAVE_TAXA.format(serie=serie.lower()))
    dia = linhas.get(CHAVE_DATA.format(serie=serie.lower()))
    data = date(dia // 10000, dia // 100 % 100, dia % 100) if dia else None
    return taxa, data


def definir_taxa(conn: sqlite3.Connection, taxa: int | None, hoje: date, serie: str = "E") -> None:
    """Grava a taxa base atual (com o dia em que foi escrita) ou apaga-a (None)."""
    chaves = (CHAVE_TAXA.format(serie=serie.lower()), CHAVE_DATA.format(serie=serie.lower()))
    with conn:
        if taxa is None:
            conn.execute("DELETE FROM configuracao WHERE chave IN (?, ?)", chaves)
            return
        for chave, valor in zip(chaves, (taxa, hoje.year * 10000 + hoje.month * 100 + hoje.day)):
            conn.execute("INSERT INTO configuracao (chave, valor) VALUES (?, ?) "
                         "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor", (chave, valor))


def resumo(conn: sqlite3.Connection) -> Resumo | None:
    """Simulação de todas as subscrições (só série E, por agora); None se não houver nenhuma."""
    subs = listar(conn)
    if not subs:
        return None
    taxa, data = obter_taxa(conn, "E")
    lista = cenarios(SERIES["E"], taxa)
    projecoes = [projetar(s, lista) for s in subs]
    return Resumo(
        projecoes=projecoes,
        cenarios=lista,
        taxa_atual=taxa,
        taxa_atual_data=data,
        valor_hoje_cent=sum(s.valor_cent for s in subs),
        total_final_cent={c.codigo: sum(p.valor_final_cent[c.codigo] for p in projecoes) for c in lista},
    )

