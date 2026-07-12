"""
collector.py — Personal Flex Tracker
Roda a cada 5 minutos via GitHub Actions + cron-job.org.

O que faz em cada ciclo:
  1. Busca as listas de Challenger, GM e Mestre para cada fila configurada
  2. Detecta variações de LP entre ciclos (= jogos terminados)
  3. Busca o LP atual do jogador configurado em cada fila
  4. Na janela de 23h40–23h55, captura o piso de LP de cada tier

Arquivos gerados:
  data/player_current.csv   — estado atual dos jogadores de elite (sobrescrito)
  data/lp_changes.csv       — variações de LP detectadas (append)
  data/my_lp.csv            — histórico de LP do jogador configurado (append)
  data/tier_floors.csv      — piso diário de LP por tier e fila (append)
  data/my_summoner.json     — cache do puuid (evita busca repetida)
"""

import csv
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from urllib.parse import quote

# Importa configurações do config.py
from config import (
    PLAYER_NAME, PLAYER_TAG, PLATFORM, REGIONAL_HOST,
    QUEUES, FLOOR_WINDOW_START, FLOOR_WINDOW_END,
)

API_KEY = os.environ.get("RIOT_API_KEY", "")
if not API_KEY:
    raise SystemExit("RIOT_API_KEY não definida.")

PLATFORM_BASE = f"https://{PLATFORM}.api.riotgames.com"
REGIONAL_BASE = f"https://{REGIONAL_HOST}.api.riotgames.com"
BRT_OFFSET    = timedelta(hours=-3)

DATA_DIR            = Path(__file__).parent / "data"
PLAYER_CURRENT_CSV  = DATA_DIR / "player_current.csv"
LP_CHANGES_CSV      = DATA_DIR / "lp_changes.csv"
MY_LP_CSV           = DATA_DIR / "my_lp.csv"
TIER_FLOORS_CSV     = DATA_DIR / "tier_floors.csv"
MY_SUMMONER_JSON    = DATA_DIR / "my_summoner.json"

PLAYER_CURRENT_HEADER = ["puuid", "tier", "lp", "wins", "losses",
                          "queue", "last_updated_utc"]
LP_CHANGES_HEADER     = ["timestamp_utc", "puuid", "tier", "queue",
                          "old_lp", "new_lp", "lp_delta"]
MY_LP_HEADER          = ["timestamp_utc", "queue", "tier", "rank",
                          "lp", "wins", "losses"]
TIER_FLOORS_HEADER    = ["date_br", "queue", "challenger_floor", "gm_floor",
                          "master_floor", "challenger_count", "gm_count",
                          "master_count", "timestamp_utc"]

session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY})
start_time = time.time()


def elapsed() -> str:
    s = int(time.time() - start_time)
    return f"{s // 60}m{s % 60:02d}s"


def get_with_retry(url: str, max_retries: int = 6) -> requests.Response:
    for attempt in range(max_retries):
        resp = session.get(url)
        if resp.status_code in (200, 404):
            return resp
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "10")) + 2
            print(f"  [{elapsed()}] Rate limit — aguardando {wait}s...", flush=True)
            time.sleep(wait)
        elif resp.status_code in (500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
        else:
            print(f"  [{elapsed()}] HTTP {resp.status_code}: {url}", flush=True)
            return resp
    raise RuntimeError(f"Falha após {max_retries} tentativas: {url}")


# ── Funções de acesso à API ───────────────────────────────────────────────────

def fetch_league(endpoint: str, queue: str) -> list[dict]:
    """Busca a lista de jogadores de um tier (challenger/grandmaster/master)."""
    url = f"{PLATFORM_BASE}/lol/league/v4/{endpoint}leagues/by-queue/{queue}"
    resp = get_with_retry(url)
    resp.raise_for_status()
    return resp.json().get("entries", [])


def get_puuid(name: str, tag: str) -> str | None:
    """Busca o puuid do jogador via account-v1 (roteamento regional)."""
    url = f"{REGIONAL_BASE}/riot/account/v1/accounts/by-riot-id/{quote(name)}/{quote(tag)}"
    resp = get_with_retry(url)
    if resp.status_code != 200:
        print(f"  [{elapsed()}] Não foi possível buscar puuid de {name}#{tag}", flush=True)
        return None
    return resp.json().get("puuid")


def get_summoner_id(puuid: str) -> str | None:
    """Busca o summonerId a partir do puuid (necessário para buscar LP)."""
    url = f"{PLATFORM_BASE}/lol/summoner/v4/summoners/by-puuid/{puuid}"
    resp = get_with_retry(url)
    if resp.status_code != 200:
        return None
    return resp.json().get("id")


def get_my_league_entries(summoner_id: str) -> list[dict]:
    """Busca as entradas de liga do jogador em todas as filas."""
    url = f"{PLATFORM_BASE}/lol/league/v4/entries/by-summoner/{summoner_id}"
    resp = get_with_retry(url)
    if resp.status_code != 200:
        return []
    return resp.json()


# ── Cache do summoner ─────────────────────────────────────────────────────────

def load_my_summoner() -> dict:
    """Carrega puuid e summonerId do cache local (evita chamadas repetidas)."""
    if MY_SUMMONER_JSON.exists():
        with MY_SUMMONER_JSON.open() as f:
            return json.load(f)
    return {}


def save_my_summoner(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with MY_SUMMONER_JSON.open("w") as f:
        json.dump(data, f, indent=2)


def resolve_my_summoner() -> dict:
    """
    Garante que temos puuid e summonerId em cache.
    Só faz chamadas à API se o cache estiver vazio.
    """
    cached = load_my_summoner()
    if cached.get("puuid") and cached.get("summoner_id"):
        return cached

    print(f"  [{elapsed()}] Resolvendo summoner: {PLAYER_NAME}#{PLAYER_TAG}...", flush=True)
    puuid = get_puuid(PLAYER_NAME, PLAYER_TAG)
    if not puuid:
        return {}

    summoner_id = get_summoner_id(puuid)
    if not summoner_id:
        return {}

    data = {
        "player_name":  PLAYER_NAME,
        "player_tag":   PLAYER_TAG,
        "puuid":        puuid,
        "summoner_id":  summoner_id,
    }
    save_my_summoner(data)
    print(f"  [{elapsed()}] Summoner resolvido e salvo em cache.", flush=True)
    return data


# ── Persistência ──────────────────────────────────────────────────────────────

def load_current() -> dict[tuple, dict]:
    """Carrega o estado atual como dict (puuid, queue) → row."""
    if not PLAYER_CURRENT_CSV.exists():
        return {}
    with PLAYER_CURRENT_CSV.open(newline="") as f:
        return {(r["puuid"], r["queue"]): r for r in csv.DictReader(f)}


def save_current(rows: list[dict]):
    """Sobrescreve player_current.csv — tamanho fixo, nunca cresce."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PLAYER_CURRENT_CSV.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PLAYER_CURRENT_HEADER, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(PLAYER_CURRENT_CSV)


def append_csv(path: Path, header: list, rows: list):
    """Acrescenta linhas a um CSV — cria o cabeçalho se o arquivo não existir."""
    if not rows:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if is_new:
            w.writeheader()
        w.writerows(rows)


def ensure_headers():
    """Cria os CSVs com cabeçalho se ainda não existirem."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, header in [
        (LP_CHANGES_CSV,  LP_CHANGES_HEADER),
        (MY_LP_CSV,       MY_LP_HEADER),
        (TIER_FLOORS_CSV, TIER_FLOORS_HEADER),
    ]:
        if not path.exists():
            with path.open("w", newline="") as f:
                csv.writer(f).writerow(header)


# ── Piso de tier ──────────────────────────────────────────────────────────────

def floor_already_captured(date_br: str, queue: str) -> bool:
    """Verifica se já gravamos o piso desta fila hoje."""
    if not TIER_FLOORS_CSV.exists():
        return False
    with TIER_FLOORS_CSV.open(newline="") as f:
        return any(
            r["date_br"] == date_br and r["queue"] == queue
            for r in csv.DictReader(f)
        )


def capture_tier_floor(
    date_br: str, queue: str,
    challengers: list, gm_players: list, masters: list,
    ts: str,
):
    """Salva o LP mínimo de cada tier para a fila e data informadas."""
    chall_lps  = sorted(e["leaguePoints"] for e in challengers if e.get("puuid"))
    gm_lps     = sorted(e["leaguePoints"] for e in gm_players  if e.get("puuid"))
    master_lps = sorted(e["leaguePoints"] for e in masters      if e.get("puuid"))

    row = {
        "date_br":          date_br,
        "queue":            queue,
        "challenger_floor": chall_lps[0]  if chall_lps  else "",
        "gm_floor":         gm_lps[0]     if gm_lps     else "",
        "master_floor":     master_lps[0] if master_lps else "",
        "challenger_count": len(challengers),
        "gm_count":         len(gm_players),
        "master_count":     len(masters),
        "timestamp_utc":    ts,
    }
    append_csv(TIER_FLOORS_CSV, TIER_FLOORS_HEADER, [row])
    print(
        f"  [{elapsed()}] 📊 Piso {queue}: "
        f"Chall={row['challenger_floor']} | "
        f"GM={row['gm_floor']} | "
        f"Mestre={row['master_floor']}",
        flush=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ensure_headers()

    now_utc = datetime.now(timezone.utc)
    now_br  = now_utc + BRT_OFFSET
    ts      = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    date_br = now_br.strftime("%Y-%m-%d")

    in_floor_window = (
        FLOOR_WINDOW_START <= (now_br.hour, now_br.minute) <= FLOOR_WINDOW_END
    )

    prev     = load_current()
    new_rows = []
    changes  = []
    totals   = {}   # queue → {"games": 0, "wins": 0, "losses": 0}

    for queue in QUEUES:
        print(f"\n[{elapsed()}] ── Fila: {queue} ──", flush=True)

        challengers = fetch_league("challenger",  queue)
        gm_players  = fetch_league("grandmaster", queue)
        masters     = fetch_league("master",      queue)

        total = len(challengers) + len(gm_players) + len(masters)
        print(
            f"[{elapsed()}] Challenger: {len(challengers)} | "
            f"GM: {len(gm_players)} | "
            f"Mestre: {len(masters)} | Total: {total}",
            flush=True,
        )

        # Captura piso de tier na janela das 23h40–23h55
        if in_floor_window and not floor_already_captured(date_br, queue):
            capture_tier_floor(date_br, queue, challengers, gm_players, masters, ts)
        elif in_floor_window:
            print(f"  [{elapsed()}] Piso de {queue} ({date_br}) já capturado.", flush=True)

        # Processa cada jogador
        games = wins = losses = 0
        all_players = (
            [(e, "challenger") for e in challengers]
            + [(e, "gm")       for e in gm_players]
            + [(e, "master")   for e in masters]
        )

        for entry, tier in all_players:
            puuid = entry.get("puuid")
            lp    = entry.get("leaguePoints", 0)
            if not puuid:
                continue

            new_rows.append({
                "puuid":            puuid,
                "tier":             tier,
                "lp":               lp,
                "wins":             entry.get("wins", 0),
                "losses":           entry.get("losses", 0),
                "queue":            queue,
                "last_updated_utc": ts,
            })

            key    = (puuid, queue)
            prev_r = prev.get(key)
            if prev_r:
                old_lp = int(prev_r["lp"])
                delta  = lp - old_lp
                if delta != 0:
                    changes.append({
                        "timestamp_utc": ts,
                        "puuid":         puuid,
                        "tier":          tier,
                        "queue":         queue,
                        "old_lp":        old_lp,
                        "new_lp":        lp,
                        "lp_delta":      delta,
                    })
                    games += 1
                    if delta > 0:
                        wins += 1
                    else:
                        losses += 1

        totals[queue] = {"games": games, "wins": wins, "losses": losses}
        print(
            f"[{elapsed()}] Jogos detectados: {games} (+{wins}W / -{losses}L)",
            flush=True,
        )

    # Busca LP do jogador configurado
    print(f"\n[{elapsed()}] ── Buscando LP de {PLAYER_NAME}#{PLAYER_TAG} ──", flush=True)
    summoner = resolve_my_summoner()
    my_lp_rows = []

    if summoner.get("summoner_id"):
        entries = get_my_league_entries(summoner["summoner_id"])
        for entry in entries:
            q = entry.get("queueType")
            if q not in QUEUES:
                continue
            my_lp_rows.append({
                "timestamp_utc": ts,
                "queue":         q,
                "tier":          entry.get("tier", ""),
                "rank":          entry.get("rank", ""),
                "lp":            entry.get("leaguePoints", 0),
                "wins":          entry.get("wins", 0),
                "losses":        entry.get("losses", 0),
            })
            print(
                f"  [{elapsed()}] {q}: "
                f"{entry.get('tier')} {entry.get('rank')} "
                f"{entry.get('leaguePoints')} LP",
                flush=True,
            )
    else:
        print(f"  [{elapsed()}] ⚠️ Summoner não resolvido — LP pessoal não registrado.", flush=True)

    # Persiste tudo
    save_current(new_rows)
    append_csv(LP_CHANGES_CSV, LP_CHANGES_HEADER, changes)
    append_csv(MY_LP_CSV,      MY_LP_HEADER,      my_lp_rows)

    print(f"\n[{elapsed()}] ✅ Concluído!", flush=True)
    for q, t in totals.items():
        print(f"  {q}: {t['games']} jogos (+{t['wins']}W / -{t['losses']}L)", flush=True)


if __name__ == "__main__":
    main()
