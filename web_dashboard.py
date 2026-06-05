import argparse
import html
import json
import os
import socket
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from repositories.database import DATABASE_FILE, init_database
from repositories.balance_repository import DATA_DIR


REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
AVALONIAN_FILE = os.path.join(DATA_DIR, "avalonian_interactions.json")
DEFAULT_LIMIT = 500
try:
    ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires") if ZoneInfo else timezone(timedelta(hours=-3))
except Exception:
    ARGENTINA_TZ = timezone(timedelta(hours=-3))


def format_number(value):
    return f"{int(value or 0):,}".replace(",", ".")


def parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def format_argentina_datetime(value):
    parsed = parse_iso_datetime(value)
    if not parsed:
        return ""

    return parsed.astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M")


def argentina_now_display():
    return datetime.now(timezone.utc).astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M")


def clean_user_name(user_name, user_id):
    text = str(user_name or "").strip()
    fallback = f"Usuario {user_id}"
    if not text or text == "Usuario" or text == fallback:
        return "Sin nombre"

    return text


def read_json_file(path, fallback):
    if not os.path.isfile(path):
        return fallback

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return fallback


def get_connection():
    init_database()
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def get_guilds(connection):
    rows = connection.execute(
        """
        SELECT guild_id, MAX(guild_name) AS guild_name
        FROM (
            SELECT guild_id, guild_name FROM economy_balances
            UNION ALL
            SELECT guild_id, guild_name FROM economy_operations
        )
        GROUP BY guild_id
        ORDER BY COALESCE(NULLIF(MAX(guild_name), ''), guild_id) COLLATE NOCASE
        """
    ).fetchall()

    guilds = []
    seen = set()
    for row in rows:
        guild_id = str(row["guild_id"])
        guild_name = row["guild_name"] or f"Servidor {guild_id}"
        guilds.append({"id": guild_id, "name": guild_name})
        seen.add(guild_id)

    for source in (read_json_file(REPORTS_FILE, {}), read_json_file(AVALONIAN_FILE, {})):
        if not isinstance(source, dict):
            continue
        for guild_id in source.keys():
            guild_id = str(guild_id)
            if guild_id not in seen:
                guilds.append({"id": guild_id, "name": f"Servidor {guild_id}"})
                seen.add(guild_id)

    return guilds


def get_balances(connection, guild_id):
    rows = connection.execute(
        """
        SELECT
            user_id,
            COALESCE(
                NULLIF(user_name, ''),
                (
                    SELECT NULLIF(player, '')
                    FROM economy_operations
                    WHERE guild_id = economy_balances.guild_id
                      AND player_id = economy_balances.user_id
                      AND NULLIF(player, '') IS NOT NULL
                      AND player != 'Usuario ' || economy_balances.user_id
                    ORDER BY id DESC
                    LIMIT 1
                ),
                (
                    SELECT NULLIF(operator, '')
                    FROM economy_operations
                    WHERE guild_id = economy_balances.guild_id
                      AND operator_id = economy_balances.user_id
                      AND NULLIF(operator, '') IS NOT NULL
                      AND operator != 'Usuario ' || economy_balances.user_id
                    ORDER BY id DESC
                    LIMIT 1
                ),
                ''
            ) AS user_name,
            items,
            silver,
            items + silver AS total,
            updated_at
        FROM economy_balances
        WHERE guild_id = ?
        ORDER BY total DESC, user_name COLLATE NOCASE, user_id
        """,
        (str(guild_id),),
    ).fetchall()

    balances = []
    for index, row in enumerate(rows, start=1):
        balance = row_to_dict(row)
        balance["rank"] = index
        balance["user_name"] = clean_user_name(balance.get("user_name"), balance.get("user_id"))
        balance["updated_at_display"] = format_argentina_datetime(balance.get("updated_at"))
        balances.append(balance)

    return balances


def get_operations(connection, guild_id, limit=DEFAULT_LIMIT):
    rows = connection.execute(
        """
        SELECT
            id,
            action,
            operator,
            operator_id,
            player,
            player_id,
            type,
            category,
            amount,
            previous_balance,
            new_balance,
            date,
            time,
            created_at
        FROM economy_operations
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(guild_id), int(limit)),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_json_records(path, guild_id, limit=DEFAULT_LIMIT):
    data = read_json_file(path, {})
    records = data.get(str(guild_id), []) if isinstance(data, dict) else []
    if not isinstance(records, list):
        return []
    return list(reversed(records[-int(limit):]))


def build_dashboard_data(guild_id=None):
    with get_connection() as connection:
        guilds = get_guilds(connection)
        requested_guild_id = str(guild_id or "")
        available_guild_ids = {guild["id"] for guild in guilds}
        if requested_guild_id and requested_guild_id in available_guild_ids:
            selected_guild_id = requested_guild_id
        else:
            selected_guild_id = guilds[0]["id"] if guilds else ""
        balances = get_balances(connection, selected_guild_id) if selected_guild_id else []
        operations = get_operations(connection, selected_guild_id) if selected_guild_id else []

    reports = get_json_records(REPORTS_FILE, selected_guild_id) if selected_guild_id else []
    avalonians = get_json_records(AVALONIAN_FILE, selected_guild_id) if selected_guild_id else []
    totals = {
        "players": len(balances),
        "items": sum(int(row["items"] or 0) for row in balances),
        "silver": sum(int(row["silver"] or 0) for row in balances),
    }
    totals["total"] = totals["items"] + totals["silver"]

    return {
        "guilds": guilds,
        "selectedGuildId": selected_guild_id,
        "balances": balances,
        "operations": operations,
        "avalonians": avalonians,
        "reports": reports,
        "totals": totals,
        "updatedAt": argentina_now_display(),
    }


INDEX_HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EconomyBot Dashboard</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #657084;
      --line: #d9e0ea;
      --brand: #0b6bcb;
      --green: #13795b;
      --gold: #9a6700;
      --red: #b42318;
      --shadow: 0 10px 28px rgba(25, 35, 55, .08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      letter-spacing: 0;
    }

    header {
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 3;
    }

    .bar {
      max-width: 1280px;
      margin: 0 auto;
      padding: 14px 18px;
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto auto;
      gap: 12px;
      align-items: center;
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }

    .controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    select, input {
      height: 36px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }

    .status {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }

    .metric strong {
      font-size: 21px;
      line-height: 1.2;
    }

    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 8px 0 12px;
    }

    .tab {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      min-height: 36px;
      padding: 0 12px;
      font: inherit;
      cursor: pointer;
    }

    .tab.active {
      border-color: var(--brand);
      background: #eaf3ff;
      color: #074d94;
      font-weight: 700;
    }

    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: auto;
      max-height: calc(100vh - 240px);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      font-size: 14px;
      vertical-align: middle;
    }

    th {
      background: #edf2f7;
      color: #27364a;
      position: sticky;
      top: 0;
      z-index: 2;
      font-size: 12px;
      text-transform: uppercase;
    }

    td.number, th.number { text-align: right; font-variant-numeric: tabular-nums; }
    tr:hover td { background: #f8fbff; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: #fff;
    }
    .add, .accepted { color: var(--green); background: #eaf7f1; border-color: #b9e2d3; }
    .remove, .rejected { color: var(--red); background: #fff0ef; border-color: #f3c0bc; }
    .silver { color: var(--gold); background: #fff7df; border-color: #eed892; }
    .items { color: var(--brand); background: #eaf3ff; border-color: #bad8f7; }

    .empty {
      padding: 26px;
      text-align: center;
      color: var(--muted);
    }

    @media (max-width: 760px) {
      .bar { grid-template-columns: 1fr; }
      .controls { justify-content: stretch; }
      select, input { width: 100%; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .table-wrap { max-height: calc(100vh - 330px); }
    }
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <h1>EconomyBot Dashboard</h1>
      <div class="controls">
        <select id="guildSelect" aria-label="Servidor"></select>
        <input id="searchInput" type="search" placeholder="Buscar" aria-label="Buscar">
      </div>
      <div id="status" class="status">Cargando...</div>
    </div>
  </header>
  <main>
    <section class="metrics" aria-label="Totales">
      <div class="metric"><span>Jugadores</span><strong id="playersTotal">0</strong></div>
      <div class="metric"><span>Items</span><strong id="itemsTotal">0</strong></div>
      <div class="metric"><span>Silver</span><strong id="silverTotal">0</strong></div>
      <div class="metric"><span>Total</span><strong id="overallTotal">0</strong></div>
    </section>

    <nav class="tabs" aria-label="Secciones">
      <button class="tab active" data-tab="balances">Balances</button>
      <button class="tab" data-tab="operations">Registro Balance</button>
      <button class="tab" data-tab="avalonians">Registro Avas</button>
      <button class="tab" data-tab="reports">Registro Informes</button>
    </nav>

    <section class="table-wrap">
      <table>
        <thead id="tableHead"></thead>
        <tbody id="tableBody"></tbody>
      </table>
      <div id="emptyState" class="empty" hidden>No hay datos para mostrar.</div>
    </section>
  </main>

  <script>
    const state = {
      data: null,
      tab: "balances",
      guildId: localStorage.getItem("dashboardGuildId") || "",
      search: ""
    };

    const columns = {
      balances: [
        ["rank", "#", "number"],
        ["user_name", "Usuario"],
        ["user_id", "ID"],
        ["items", "Items", "number"],
        ["silver", "Silver", "number"],
        ["total", "Total", "number"],
        ["updated_at_display", "Fecha"]
      ],
      operations: [
        ["action", "Accion"],
        ["operator", "Operador"],
        ["player", "Jugador"],
        ["type", "Tipo"],
        ["category", "Categoria"],
        ["amount", "Cantidad", "number"],
        ["previous_balance", "Anterior", "number"],
        ["new_balance", "Nuevo", "number"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      avalonians: [
        ["ava", "Ava"],
        ["action", "Accion"],
        ["user", "Usuario"],
        ["user_id", "ID"],
        ["slot", "Cupo"],
        ["reason", "Justificacion"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      reports: [
        ["ava", "Ava"],
        ["caller", "Caller"],
        ["caller_id", "ID Caller"],
        ["reviewer", "Revisado por"],
        ["decision", "Decision"],
        ["reason", "Motivo"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ]
    };

    const numberFields = new Set(["items", "silver", "total", "amount", "previous_balance", "new_balance"]);

    function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString("es-AR") : value;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function badge(value, field) {
      const text = String(value ?? "");
      const lowered = text.toLowerCase();
      let cls = "";
      if (field === "type" || field === "action") {
        if (lowered.includes("add") || lowered.includes("signup")) cls = "add";
        if (lowered.includes("remove") || lowered.includes("leave")) cls = "remove";
      }
      if (field === "category") {
        if (lowered.includes("silver")) cls = "silver";
        if (lowered.includes("items")) cls = "items";
      }
      if (field === "decision") {
        if (lowered.includes("acept")) cls = "accepted";
        if (lowered.includes("rechaz")) cls = "rejected";
      }
      return cls ? `<span class="pill ${cls}">${escapeHtml(text)}</span>` : escapeHtml(text);
    }

    function activeRows() {
      if (!state.data) return [];
      const rows = state.data[state.tab] || [];
      const query = state.search.trim().toLowerCase();
      if (!query) return rows;
      return rows.filter(row => JSON.stringify(row).toLowerCase().includes(query));
    }

    function renderGuilds() {
      const select = document.getElementById("guildSelect");
      const guilds = state.data?.guilds || [];
      select.innerHTML = guilds.map(guild => {
        const selected = guild.id === state.data.selectedGuildId ? " selected" : "";
        return `<option value="${escapeHtml(guild.id)}"${selected}>${escapeHtml(guild.name)} (${escapeHtml(guild.id)})</option>`;
      }).join("");
    }

    function renderMetrics() {
      const totals = state.data?.totals || {};
      document.getElementById("playersTotal").textContent = formatNumber(totals.players);
      document.getElementById("itemsTotal").textContent = formatNumber(totals.items);
      document.getElementById("silverTotal").textContent = formatNumber(totals.silver);
      document.getElementById("overallTotal").textContent = formatNumber(totals.total);
    }

    function renderTable() {
      const head = document.getElementById("tableHead");
      const body = document.getElementById("tableBody");
      const empty = document.getElementById("emptyState");
      const selectedColumns = columns[state.tab];
      const rows = activeRows();

      head.innerHTML = `<tr>${selectedColumns.map(([, label, cls]) => `<th class="${cls || ""}">${label}</th>`).join("")}</tr>`;
      body.innerHTML = rows.map(row => {
        const cells = selectedColumns.map(([field, , cls]) => {
          const raw = row[field] ?? "";
          const value = numberFields.has(field) ? formatNumber(raw) : badge(raw, field);
          return `<td class="${cls || ""}">${value}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      }).join("");
      empty.hidden = rows.length > 0;
    }

    function render() {
      renderGuilds();
      renderMetrics();
      renderTable();
      document.querySelectorAll(".tab").forEach(button => {
        button.classList.toggle("active", button.dataset.tab === state.tab);
      });
      const status = document.getElementById("status");
      status.textContent = state.data ? `Refrescado ${state.data.updatedAt}` : "Sin datos";
    }

    async function loadData() {
      const params = new URLSearchParams();
      if (state.guildId) params.set("guild_id", state.guildId);
      const response = await fetch(`/api/data?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) throw new Error("No se pudo cargar la informacion.");
      state.data = await response.json();
      state.guildId = state.data.selectedGuildId || "";
      if (state.guildId) localStorage.setItem("dashboardGuildId", state.guildId);
      render();
    }

    document.getElementById("guildSelect").addEventListener("change", event => {
      state.guildId = event.target.value;
      localStorage.setItem("dashboardGuildId", state.guildId);
      loadData().catch(showError);
    });

    document.getElementById("searchInput").addEventListener("input", event => {
      state.search = event.target.value;
      renderTable();
    });

    document.querySelectorAll(".tab").forEach(button => {
      button.addEventListener("click", () => {
        state.tab = button.dataset.tab;
        render();
      });
    });

    function showError(error) {
      document.getElementById("status").textContent = error.message;
    }

    loadData().catch(showError);
    setInterval(() => loadData().catch(showError), 3000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def send_text(self, status, content, content_type):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, status, data):
        self.send_text(status, json.dumps(data, ensure_ascii=False), "application/json")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_text(200, INDEX_HTML, "text/html")
            return

        if parsed.path == "/api/data":
            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            try:
                self.send_json(200, build_dashboard_data(guild_id))
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        self.send_text(404, "No encontrado", "text/plain")

    def log_message(self, format, *args):
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = html.escape(format % args)
        print(f"[{timestamp}] {self.address_string()} {message}")


def parse_args():
    parser = argparse.ArgumentParser(description="Dashboard local de EconomyBot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def build_servers(host, port):
    requested_host = str(host or "").strip().lower()
    hosts = [host]
    if requested_host in ("127.0.0.1", "localhost"):
        hosts = ["127.0.0.1", "::1"]

    servers = []
    for bind_host in hosts:
        server_class = IPv6ThreadingHTTPServer if ":" in bind_host else ThreadingHTTPServer
        try:
            servers.append(server_class((bind_host, port), DashboardHandler))
        except OSError:
            for server in servers:
                server.server_close()
            raise

    return servers


def main():
    args = parse_args()
    servers = build_servers(args.host, args.port)
    print(f"Dashboard disponible en http://localhost:{args.port}")
    print(f"Tambien disponible en http://127.0.0.1:{args.port}")
    print("Presiona Ctrl+C para detenerlo.")
    try:
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
