"""
dashboard.py — Personal Flex Tracker v1

Abas:
  🏆 Meu Progresso   — LP pessoal vs linhas de corte Challenger/GM
  🔥 Heatmap         — atividade dos jogadores de elite por horário
  📈 Série Temporal  — evolução de jogos detectados ao longo do tempo
  🗃️  Dados Brutos    — acesso direto aos CSVs
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from config import (
    PLAYER_NAME, PLAYER_TAG, QUEUES, QUEUE_LABELS,
    TIER_COLORS, QUEUE_COLORS, DIVISION_OFFSETS, LP_PER_DIVISION,
)

# ── Arquivos ──────────────────────────────────────────────────────────────────
DATA_DIR           = Path(__file__).parent / "data"
PLAYER_CURRENT_CSV = DATA_DIR / "player_current.csv"
LP_CHANGES_CSV     = DATA_DIR / "lp_changes.csv"
MY_LP_CSV          = DATA_DIR / "my_lp.csv"
TIER_FLOORS_CSV    = DATA_DIR / "tier_floors.csv"

# ── Constantes ────────────────────────────────────────────────────────────────
DIAS_PT    = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",
              4:"Sexta",5:"Sábado",6:"Domingo"}
ORDEM_DIAS = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"]

TIER_LABELS = {
    "challenger": "Challenger",
    "gm":         "Grão-Mestre",
    "master":     "Mestre",
}

# Ordem de severidade dos tiers (para colorir linha do jogador)
TIER_ORDER = ["IRON","BRONZE","SILVER","GOLD","PLATINUM","EMERALD",
              "DIAMOND","MASTER","GRANDMASTER","CHALLENGER"]

RANK_OFFSET = {"I": 0, "II": -100, "III": -200, "IV": -300}

# ── Conversão de LP para escala do gráfico ────────────────────────────────────
def to_chart_lp(tier: str, rank: str, lp: int) -> float:
    """
    Converte tier/rank/LP para a escala do gráfico de progresso.
    Master 0 LP = 0. Tiers abaixo de Master = valores negativos.
    GM e Challenger ficam acima de 0, na mesma escala de LP.
    """
    t = tier.upper() if tier else ""
    if t in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        return float(lp)
    base   = DIVISION_OFFSETS.get(t, -2500)
    r_off  = RANK_OFFSET.get(rank.upper() if rank else "", 0)
    return float(base + r_off + lp)

# ── Loaders ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_changes() -> pd.DataFrame:
    if not LP_CHANGES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(LP_CHANGES_CSV)
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["timestamp_br"]  = df["timestamp_utc"].dt.tz_convert("America/Sao_Paulo")
    return df


@st.cache_data(ttl=60)
def load_my_lp() -> pd.DataFrame:
    if not MY_LP_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(MY_LP_CSV)
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["timestamp_br"]  = df["timestamp_utc"].dt.tz_convert("America/Sao_Paulo")
    df["chart_lp"]      = df.apply(
        lambda r: to_chart_lp(r["tier"], r["rank"], r["lp"]), axis=1
    )
    df["winrate"] = (
        df["wins"] / (df["wins"] + df["losses"]).replace(0, pd.NA) * 100
    ).round(1)
    return df


@st.cache_data(ttl=300)
def load_tier_floors() -> pd.DataFrame:
    if not TIER_FLOORS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TIER_FLOORS_CSV)
    if df.empty:
        return df
    df["date_br"] = pd.to_datetime(df["date_br"])
    for col in ["challenger_floor", "gm_floor", "master_floor"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date_br")


@st.cache_data(ttl=60)
def compute_heatmap(changes_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Soma de jogos nos últimos 30 min por slot de 5 min, deslocado -30 min."""
    if changes_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = changes_df.copy()
    df["window"] = df["timestamp_br"].dt.floor("5min")
    counts = df.groupby("window").size().reset_index(name="n")
    if len(counts) > 1:
        full_range = pd.date_range(
            start=counts["window"].min(),
            end=counts["window"].max(),
            freq="5min", tz="America/Sao_Paulo",
        )
        counts = (
            counts.set_index("window")
            .reindex(full_range, fill_value=0)
            .rename_axis("window").reset_index()
        )
    counts = counts.sort_values("window")
    counts["rolling"]       = counts["n"].rolling(window=6, min_periods=1).sum()
    counts["window_inicio"] = counts["window"] - pd.Timedelta(minutes=30)
    counts["dia_semana"]    = counts["window_inicio"].dt.weekday.map(DIAS_PT)
    counts["slot_5min"]     = (
        counts["window_inicio"].dt.hour * 12
        + counts["window_inicio"].dt.minute // 5
    )
    pivot = (
        counts.groupby(["dia_semana", "slot_5min"])["rolling"]
        .mean().reset_index()
        .pivot(index="dia_semana", columns="slot_5min", values="rolling")
        .reindex(ORDEM_DIAS)
        .reindex(columns=list(range(288)), fill_value=0)
    )
    return pivot, counts


def slot_to_timestr(slot: int) -> str:
    return f"{slot // 12:02d}:{(slot % 12) * 5:02d}"


def render_heatmap_fig(pivot: pd.DataFrame) -> go.Figure:
    pivot_plot = pivot.copy()
    pivot_plot.columns = [slot_to_timestr(int(c)) for c in pivot_plot.columns]
    tick_pos    = [slot_to_timestr(s) for s in range(0, 288, 12)]
    tick_labels = [f"{h:02d}h" for h in range(24)]
    fig = px.imshow(
        pivot_plot,
        labels=dict(x="Horário (Brasília)", y="", color="Jogos / 30 min"),
        color_continuous_scale="Reds",
        aspect="auto", zmin=0,
    )
    fig.update_xaxes(
        tickvals=tick_pos, ticktext=tick_labels,
        showgrid=True, gridcolor="rgba(255,255,255,0.1)",
    )
    fig.update_layout(
        height=300, margin=dict(l=10,r=10,t=10,b=10),
        coloraxis_colorbar=dict(thickness=15),
    )
    return fig

# ── Layout ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=f"Personal Flex Tracker — {PLAYER_NAME}",
    page_icon="🏆", layout="wide",
)
st.title(f"🏆 Personal Flex Tracker — {PLAYER_NAME}#{PLAYER_TAG}")
st.caption("Monitoramento pessoal de LP + atividade dos jogadores de elite no BR")

# Carrega dados
changes_df = load_changes()
my_lp_df   = load_my_lp()
floors_df  = load_tier_floors()

# Métricas de topo
c1, c2, c3, c4 = st.columns(4)

if not my_lp_df.empty:
    ultimo = my_lp_df.sort_values("timestamp_br").groupby("queue").last().reset_index()
    for i, row in ultimo.iterrows():
        col = [c1, c2][i % 2]
        ql  = QUEUE_LABELS.get(row["queue"], row["queue"])
        col.metric(
            f"{ql}",
            f"{row['tier']} {row['rank']} — {int(row['lp'])} LP",
            f"WR {row['winrate']:.0f}%  ({int(row['wins'])}V/{int(row['losses'])}D)",
        )
else:
    c1.metric("LP", "—")
    c2.metric("Filas", ", ".join(QUEUE_LABELS.get(q,q) for q in QUEUES))

c3.metric(
    "Última coleta",
    my_lp_df["timestamp_br"].max().strftime("%d/%m %H:%M")
    if not my_lp_df.empty else "—",
)
c4.metric(
    "Jogos elite detectados (total)",
    len(changes_df) if not changes_df.empty else "—",
)

st.divider()

tab_prog, tab_heat, tab_serie, tab_raw = st.tabs([
    "🏆 Meu Progresso",
    "🔥 Heatmap",
    "📈 Série Temporal",
    "🗃️ Dados Brutos",
])

# ════════════════════════════════════════════════════════════════════════════
# 🏆 MEU PROGRESSO
# ════════════════════════════════════════════════════════════════════════════
with tab_prog:
    st.subheader("Evolução de LP e linhas de corte de tier")
    st.caption(
        "Eixo Y: LP relativo a Mestre 0 LP (zero do gráfico). "
        "Tiers abaixo de Mestre aparecem como valores negativos. "
        "As linhas pontilhadas mostram o LP mínimo para entrar em cada tier."
    )

    if my_lp_df.empty:
        st.info("Aguardando primeira coleta de LP pessoal...")
        st.stop()

    queue_sel = st.multiselect(
        "Fila:",
        options=QUEUES,
        default=QUEUES,
        format_func=lambda q: QUEUE_LABELS.get(q, q),
        key="queue_prog",
    )

    for queue in queue_sel:
        ql       = QUEUE_LABELS.get(queue, queue)
        my_q     = my_lp_df[my_lp_df["queue"] == queue].sort_values("timestamp_br")
        floors_q = floors_df[floors_df["queue"] == queue].sort_values("date_br") \
                   if not floors_df.empty and "queue" in floors_df.columns \
                   else pd.DataFrame()

        st.subheader(f"{'🔵' if 'SOLO' in queue else '🟢'} {ql}")

        if my_q.empty:
            st.info(f"Sem dados de LP para {ql} ainda.")
            continue

        fig = go.Figure()

        # ── Linhas de corte de tier ──────────────────────────────────────
        if not floors_q.empty:
            # GM floor
            fig.add_trace(go.Scatter(
                x=floors_q["date_br"],
                y=floors_q["gm_floor"],
                mode="lines",
                name="Piso Grão-Mestre",
                line=dict(color=TIER_COLORS["gm"], width=1.5, dash="dot"),
                hovertemplate="Piso GM: %{y} LP<br>%{x|%d/%m}<extra></extra>",
            ))
            # Challenger floor
            fig.add_trace(go.Scatter(
                x=floors_q["date_br"],
                y=floors_q["challenger_floor"],
                mode="lines",
                name="Piso Challenger",
                line=dict(color=TIER_COLORS["challenger"], width=1.5, dash="dot"),
                hovertemplate="Piso Chall: %{y} LP<br>%{x|%d/%m}<extra></extra>",
            ))

        # ── LP do jogador ────────────────────────────────────────────────
        fig.add_trace(go.Scatter(
            x=my_q["timestamp_br"],
            y=my_q["chart_lp"],
            mode="lines+markers",
            name=f"{PLAYER_NAME}#{PLAYER_TAG}",
            line=dict(color=QUEUE_COLORS.get(queue, "#ffffff"), width=2.5),
            marker=dict(size=5),
            hovertemplate=(
                "<b>%{customdata[0]} %{customdata[1]}</b> — %{customdata[2]} LP<br>"
                "%{x|%d/%m %H:%M}<extra></extra>"
            ),
            customdata=my_q[["tier","rank","lp"]].values,
        ))

        # ── Linha de referência: Mestre 0 LP ────────────────────────────
        x_range = list(my_q["timestamp_br"])
        if not floors_q.empty:
            x_range = x_range + list(floors_q["date_br"])
        if x_range:
            fig.add_hline(
                y=0, line_dash="dash",
                line_color="rgba(255,255,255,0.3)",
                annotation_text="Mestre 0 LP",
                annotation_position="right",
            )

        # ── Anotações de tier no eixo Y ──────────────────────────────────
        tier_annotations = [
            (0,    "Mestre"),
            (-100, "Diamante 1"),
            (-200, "Diamante 2"),
            (-300, "Diamante 3"),
            (-400, "Diamante 4"),
            (-500, "Esmeralda 1"),
        ]
        for y_val, label in tier_annotations:
            fig.add_annotation(
                x=0, y=y_val, xref="paper", yref="y",
                text=label, showarrow=False,
                font=dict(size=10, color="rgba(255,255,255,0.4)"),
                xanchor="left",
            )

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            yaxis_title="LP (relativo a Mestre 0)",
            xaxis_title="Data/Hora (Brasília)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Métricas de distância ─────────────────────────────────────────
        if not my_q.empty and not floors_q.empty:
            ultimo_lp   = my_q.iloc[-1]["chart_lp"]
            ultimo_floor = floors_q.iloc[-1]
            gm_floor    = ultimo_floor["gm_floor"]
            chall_floor = ultimo_floor["challenger_floor"]

            m1, m2, m3 = st.columns(3)
            m1.metric(
                "LP atual (escala Master)",
                f"{ultimo_lp:+.0f}",
            )
            m2.metric(
                "Distância para GM",
                f"{gm_floor - ultimo_lp:+.0f} LP",
                help=f"Piso atual de GM: {gm_floor} LP",
            )
            m3.metric(
                "Distância para Challenger",
                f"{chall_floor - ultimo_lp:+.0f} LP",
                help=f"Piso atual de Challenger: {chall_floor} LP",
            )


        # ── Gráfico de quantidade de jogadores por tier ───────────────────
        if not floors_q.empty:
            st.subheader("Quantidade de jogadores por tier")
            st.caption(
                "Capturado diariamente às 23h45. "
                "Mostra quantos jogadores estavam em cada tier no momento da atualização das listas."
            )

            count_cols = {
                "challenger_count": ("Challenger", TIER_COLORS["challenger"]),
                "gm_count":         ("Grão-Mestre", TIER_COLORS["gm"]),
                "master_count":     ("Mestre", TIER_COLORS["master"]),
            }

            fig_count = go.Figure()
            for col, (label, color) in count_cols.items():
                if col in floors_q.columns:
                    fig_count.add_trace(go.Bar(
                        x=floors_q["date_br"],
                        y=floors_q[col],
                        name=label,
                        marker_color=color,
                        hovertemplate=f"{label}: %{{y}} jogadores<br>%{{x|%d/%m}}<extra></extra>",
                    ))

            fig_count.update_layout(
                barmode="group",
                height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                yaxis_title="Nº de jogadores",
                xaxis_title="Data",
                hovermode="x unified",
            )
            st.plotly_chart(fig_count, use_container_width=True)

        st.divider()


# ════════════════════════════════════════════════════════════════════════════
# 🔥 HEATMAP
# ════════════════════════════════════════════════════════════════════════════
with tab_heat:
    st.subheader("Heatmap de atividade — início estimado das partidas")
    st.caption(
        "**Cada célula = 5 min.** Soma de jogos detectados nos 30 min anteriores, "
        "deslocada -30 min (estima entrada na fila, não fim do jogo)."
    )

    tier_sel = st.multiselect(
        "Tiers:", options=["challenger","gm","master"],
        default=["challenger","gm","master"],
        format_func=lambda t: TIER_LABELS.get(t, t), key="tier_heat",
    )
    queue_heat = st.multiselect(
        "Fila:", options=QUEUES, default=QUEUES,
        format_func=lambda q: QUEUE_LABELS.get(q, q), key="queue_heat",
    )

    if changes_df.empty:
        st.info("Aguardando ao menos 2 ciclos de coleta.")
    else:
        filtered = changes_df[
            changes_df["tier"].isin(tier_sel) &
            changes_df["queue"].isin(queue_heat)
        ]
        pivot, series = compute_heatmap(filtered)

        if pivot.empty:
            st.info("Dados insuficientes para o heatmap.")
        else:
            st.plotly_chart(render_heatmap_fig(pivot), use_container_width=True)

            st.subheader("⚠️ Top 10 momentos mais movimentados")
            top = pivot.copy()
            top.columns = [slot_to_timestr(int(c)) for c in top.columns]
            top = top.stack().reset_index()
            top.columns = ["dia", "horário", "média"]
            top = top.sort_values("média", ascending=False).head(10).reset_index(drop=True)
            top.index += 1
            top["média"] = top["média"].round(2)
            st.dataframe(top, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# 📈 SÉRIE TEMPORAL
# ════════════════════════════════════════════════════════════════════════════
with tab_serie:
    if changes_df.empty:
        st.info("Aguardando dados...")
    else:
        tier_sel_s = st.multiselect(
            "Tiers:", options=["challenger","gm","master"],
            default=["challenger","gm","master"],
            format_func=lambda t: TIER_LABELS.get(t, t), key="tier_serie",
        )
        queue_sel_s = st.multiselect(
            "Fila:", options=QUEUES, default=QUEUES,
            format_func=lambda q: QUEUE_LABELS.get(q, q), key="queue_serie",
        )

        filtered_s = changes_df[
            changes_df["tier"].isin(tier_sel_s) &
            changes_df["queue"].isin(queue_sel_s)
        ]

        st.subheader("Jogos detectados por hora")
        hourly = (
            filtered_s.groupby([
                filtered_s["timestamp_br"].dt.floor("h"), "queue"
            ]).size().reset_index(name="jogos")
        )
        hourly["fila"] = hourly["queue"].map(QUEUE_LABELS)
        fig_h = px.bar(
            hourly, x="timestamp_br", y="jogos", color="fila",
            color_discrete_map={v: QUEUE_COLORS[k] for k,v in QUEUE_LABELS.items()},
            labels={"timestamp_br":"Hora (Brasília)","jogos":"Jogos","fila":"Fila"},
            barmode="stack",
        )
        fig_h.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_h, use_container_width=True)

        st.subheader("Vitórias e derrotas inferidas")
        fs2 = filtered_s.copy()
        fs2["resultado"] = fs2["lp_delta"].apply(
            lambda d: "Vitória (LP↑)" if d > 0 else "Derrota (LP↓)"
        )
        h2 = (
            fs2.groupby([fs2["timestamp_br"].dt.floor("h"), "resultado"])
            .size().reset_index(name="n")
        )
        fig_vd = px.bar(
            h2, x="timestamp_br", y="n", color="resultado",
            color_discrete_map={"Vitória (LP↑)":"#4ade80","Derrota (LP↓)":"#f87171"},
            barmode="stack",
            labels={"timestamp_br":"Hora (Brasília)","n":"Partidas"},
        )
        fig_vd.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_vd, use_container_width=True)

        st.subheader("Soma de 30 min (com deslocamento -30 min)")
        _, series_s = compute_heatmap(filtered_s)
        if not series_s.empty:
            fig_roll = px.line(
                series_s.dropna(subset=["rolling"]),
                x="window_inicio", y="rolling",
                labels={"window_inicio":"Início estimado (Brasília)",
                        "rolling":"Jogos / 30 min"},
                color_discrete_sequence=["#3b82f6"],
            )
            fig_roll.update_layout(height=260, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_roll, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# 🗃️ DADOS BRUTOS
# ════════════════════════════════════════════════════════════════════════════
with tab_raw:
    sub1, sub2, sub3 = st.tabs(["Meu LP", "Mudanças elite", "Piso de Tier"])

    with sub1:
        if my_lp_df.empty:
            st.info("Sem dados.")
        else:
            n = st.slider("Últimos N registros:", 20, 200, 50, key="n_mylp")
            st.dataframe(
                my_lp_df[["timestamp_br","queue","tier","rank","lp","wins","losses","winrate"]]
                .sort_values("timestamp_br", ascending=False).head(n)
                .reset_index(drop=True),
                use_container_width=True,
            )

    with sub2:
        if changes_df.empty:
            st.info("Sem dados.")
        else:
            n2 = st.slider("Últimas N mudanças:", 50, 500, 100, key="n_changes")
            st.dataframe(
                changes_df[["timestamp_br","queue","tier","old_lp","new_lp","lp_delta"]]
                .sort_values("timestamp_br", ascending=False).head(n2)
                .reset_index(drop=True),
                use_container_width=True,
            )

    with sub3:
        if floors_df.empty:
            st.info("Sem dados de piso ainda (capturado às 23h40–23h55).")
        else:
            st.dataframe(
                floors_df.sort_values("date_br", ascending=False)
                .reset_index(drop=True),
                use_container_width=True,
            )
