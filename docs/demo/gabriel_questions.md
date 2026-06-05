# Gabriel — frågor & svar

## Innehållsförteckning

- [VG-krav i korthet](#vg-krav-i-korthet)
- [Vad får varje agent / sub-agent göra?](#vad-får-varje-agent--sub-agent-göra)
  - [Vilken modell kör varje agent?](#vilken-modell-kör-varje-agent)
- [Hur väl funkar `edit_file`, och vilket tool används?](#hur-väl-funkar-edit_file-och-vilket-tool-används-egenbyggt-oss-tool-eller-os-primitiver)
  - [Hur väl fungerar det?](#hur-väl-fungerar-det)
  - [Sammanfattning](#sammanfattning)
- [Är "diffen" vid filredigering `git diff` eller ett eget verktyg?](#är-diffen-vid-filredigering-git-diff-eller-ett-eget-verktyg)
- [Vad händer om agenten eller jag gör `ssh`?](#vad-händer-om-agenten-eller-jag-gör-ssh)
- [Kan agenten nå resurser på nätverket?](#kan-agenten-nå-resurser-på-nätverket)

## VG-krav i korthet

Källa: `docs/background/vg_assignment_grading_requirements.md` (§1 hard gates,
§2 minimum feature set). Varje feature räknas **bara** om den *demonstreras live*.

| # | Krav | MET när |
|---|------|---------|
| **HG-0** | Artefakter inladdade | Spec, build och demo-evidens faktiskt öppnade och citerbara |
| **HG-1** | Egen godkänd spec | Studenten skrev en kravspec som examinatorn godkänt |
| **HG-2** | Promptad, ej handskriven kod | Lösningen promptades fram; chatt-sessionerna kan visas |
| **HG-3** | Arkitekturförståelse | Studenten kan förklara systemet på arkitekturnivå (styrkor/svagheter) |
| **HG-4** | Demonstrerad live | Lösningen visad körande live (eller via inspelning/avatar) |
| **VG.1** | Parallella sub-agenter | Main-agenten startar 2+ sub-agenter parallellt **och** använder resultaten |
| **VG.2** | Avancerad context-engineering | Konkret mekanism håller context-fönstret nere (t.ex. compaction) |
| **VG.3** | Kostnadsmonitorering + budget | Realtidskostnad + varningströskel + **hård cap som stoppar** agenten |
| **VG.4** | Skydd mot skadliga tool-calls | Destruktiva anrop blockeras/grindas *före* exekvering (allow/deny-list) |
| **VG.5** | Bash-exekvering | Agenten kör riktiga shell-kommandon (täckt av VG.4-grinden) |
| **VG.6** | Partiell filredigering | Agenten redigerar en *sektion* av en fil, inte bara helfils-overwrite |
| **VG.7** | Deploybar paketering | Ren, dokumenterad install/run-väg (t.ex. Docker + README) |
| **VG.8** | Config-fil + env-secrets | All config i fil; alla secrets från env-vars; inga committade nycklar |
| **VG.9** | Agent-autonomi | Agenten väljer själv varje tur: anropa nytt verktyg eller yield:a |

**Verdict-regel:** VG ges iff alla hard gates passerar **och** VG.1–VG.9 är MET
(vid goldcoin-justerad bar) **och** substansgrinden §4b är all-YES **och** live-demon
var tillfredsställande.

## Vad får varje agent / sub-agent göra?

Källa: `PROMPTS.md`. Parenten är den enda som dispatchar; sub-agenterna är
typade och bundna. `MAX_SUBAGENT_DEPTH = 1` → ingen sub-agent får spawna nästa.

| Agent | Roll | Verktyg (kan) | Får / får inte (constraints) |
|-------|------|---------------|------------------------------|
| **Parent** | Orkestrerar hela uppgiften, bestämmer varje transition | `read_file`, `read_file_range`, `run_bash`, `run_tests`, `spawn_subagent`, `spawn_subagents` | Läser men **redigerar aldrig** filer själv (`write_file`/`edit_file` finns bara i Coder). `run_bash` = **en** read-only kommando *eller* exakt `rm <fil>`. Inga pipes/redirect/kedjor/pytest/Python. Använd `run_tests`, ej `run_bash pytest`. |
| **Grilling** | Reder ut tvetydig uppgift | **Inga verktyg** | Returnerar bara JSON: `{"refined_task": …}` eller upp till 3 skarpa frågor. Inga kosmetiska frågor. |
| **Explorer** | Read-only inspektion av avgränsat område | Read-only verktyg (`read_file`, `read_file_range`, `run_bash` allowlist) | Returnerar **en** summary ≤ 2 KB. Får **inte** redigera filer eller spawna sub-agent. Intermediära tool-calls stannar i privat kontext. |
| **Coder** | Minsta möjliga kodändring | `read_file`, `read_file_range`, `write_file`, `edit_file`, `run_tests`, `run_bash` (endast `py_compile`) | **Enda** agenten som får mutera filer. Måste skriva minst en gång vid create/fix/add/test (read-only exit = fail). Prefererar `edit_file`. Uppdaterar alla referenser efter rename. Ingen godtycklig Python via `run_bash`. |
| **Reviewer** | Verifierar en Coder-ändring | `read_file`, `read_file_range`, `run_bash` (allowlist + `py_compile`) | **Måste** läsa ändrad fil på disk först. **Max 2 tool-calls**, sedan `PASS:`/`FAIL:`. Får **inte** ändra filer eller spawna sub-agent. Verifierar bara en färsk Coder-ändring (annars Explorer). |

**Pipeline-regler i korthet:** tvetydig uppgift → Grilling. Inspektion →
Explorer (parallellt via `spawn_subagents`). Ändra befintlig kod → Explorer →
Coder → **obligatorisk Reviewer** → `run_tests`. Greenfield (ny fil, inga
anropare) → Coder + `py_compile`-självkoll → **obligatorisk Reviewer** (varje
Coder med `writes_ok > 0` granskas; enda undantaget är parentens sista
reserverade steg). Radering → `run_bash rm <fil>` via approval-grinden.

### Vilken modell kör varje agent?

Källa: `MODEL_CONFIG.md`. Varje roll har en egen modell-id; alla går via LiteLLM
mot OpenRouter. Compactor är inte en sub-agent i pipelinen utan modellen som kör
parent-scoped compaction (summerar `tool_result` som överstiger `K_COMPACT`).

| Agent / roll | Default-profil (`MODEL_CONFIG.md`) | Aktiv demo-profil (Sonnet-parent + Haiku-coder) |
|--------------|-------------------------------------|--------------------------------------------------|
| **Parent** | `openrouter/google/gemini-2.5-flash` | `openrouter/anthropic/claude-sonnet-4.6` |
| **Grilling** | `openrouter/google/gemini-2.5-flash` | `openrouter/google/gemini-2.5-flash-lite` |
| **Explorer** | `openrouter/google/gemini-2.5-flash` | `openrouter/google/gemini-2.5-flash-lite` |
| **Coder** | `openrouter/anthropic/claude-haiku-4.5` | `openrouter/anthropic/claude-haiku-4.5` |
| **Reviewer** | `openrouter/google/gemini-2.5-flash` | `openrouter/anthropic/claude-haiku-4.5` |
| **Compactor** | `openrouter/google/gemini-2.5-flash` | `openrouter/google/gemini-2.5-flash-lite` |

**Designval:** läs-tunga roller (Parent, Grilling, Explorer, Reviewer, Compactor)
körs på billiga Gemini-flash-modeller; **Coder** får en starkare Haiku-modell för
att minska tomma coder-turns och hallucinerade API:er. Varje id kan överridas via
`VG_PARENT_MODEL`, `VG_CODER_MODEL`, `VG_REVIEWER_MODEL`, `VG_EXPLORER_MODEL`,
`VG_GRILLING_MODEL`, `VG_COMPACTOR_MODEL` (eller `workspace/config.toml` / CLI-flaggor).



## Hur väl funkar `edit_file`, och vilket tool används? (egenbyggt, OSS-tool, eller OS-primitiver?)

**Vilket verktyg används?** Egenbyggt, ovanpå Python-stdlib. Inget OSS-bibliotek,
ingen OS-primitiv (inget `sed`/`patch`). Hela operationen är ~12 rader i
`scripts/templates/tools.py.tmpl:388` (renderas till `src/vg_agent/tools.py`):

```python
content = path.read_text(encoding="utf-8")
occurrences = content.count(old)
if occurrences == 0:
    return ... "old text not found" ...
path.write_text(content.replace(old, new), encoding="utf-8", newline="\n")
```

Kärnan är alltså Pythons inbyggda `str.count` + `str.replace` — en **literal
sträng-substitution**, inte en diff/patch-motor och ingen fuzzy-matchning.

### Hur väl fungerar det?

**Styrkor:**

- **Säkerhet först** — `validate_sensitive_path` + `resolve_workspace_path` körs
  före all I/O, så absoluta sökvägar och `..`-traversering avvisas (samma garanti
  som övriga filverktyg).
- **Deterministiskt och förutsägbart** — literal match, inga regex-överraskningar.
- **Normaliserar radslut** — skriver alltid `newline="\n"`, vilket är medvetet på
  en Windows-repo.
- **Rapporterar antal träffar** — returnerar `replaced N occurrence(s)`, så
  anroparen ser om bytet var bredare än väntat.
- **Tydligt fel vid miss** — `0 occurrences` → `error`, ingen tyst no-op.

**Svagheter / skarpa kanter (jämfört med en mogen editor):**

1. **Ingen unikhetskontroll.** Den byter **alla** förekomster av `old` utan att
   fråga. Om `old` inte är unik får du oavsiktliga ändringar — enda signalen är
   `occurrences`-räknaren i efterhand.
2. **Ingen fuzzy/whitespace-tolerans.** Måste matcha byte-för-byte. Felaktig
   indentering eller avvikande radslut → `old text not found`.
3. **Hela filen läses/skrivs i minnet.** Bra för källfiler, mindre lämpligt för
   riktigt stora filer.
4. **`read_text(encoding="utf-8")`** — icke-UTF8-filer faller på `OSError/ValueError`
   och returnerar `error` (hanteras, kraschar inte).

### Sammanfattning

Det är ett **medvetet minimalistiskt, egenbyggt verktyg** — stdlib-strängoperationer
inramade av repos säkerhetsgrindar. Det passar agentens designfilosofi (agent-skalet,
inte modellkvaliteten, är VG-anspråket): litet, granskningsbart, deny-by-default. Den
huvudsakliga funktionella bristen relativt en mogen editor är **"replace-all utan
unikhetskrav"** — fungerar utmärkt när modellen ger en tillräckligt specifik
`old`-sträng, men saknar skyddsräcket som tvingar fram unika matchningar.

## Är "diffen" vid filredigering `git diff` eller ett eget verktyg?

**Kort svar:** Eget. Diffen som visas vid `write_file`/`edit_file` anropar
**aldrig** `git`. Den genereras av Pythons stdlib `difflib.unified_diff` i
`src/vg_agent/chat_ui.py:1100` (`format_unified_diff`):

```python
difflib.unified_diff(
    old.splitlines(),
    new.splitlines(),
    fromfile=f"a/{path}",   # git-stil-header, men ingen git inblandad
    tofile=f"b/{path}",
    lineterm="",
    n=DIFF_CONTEXT_LINES,   # 3 kontextrader
)
```

**Varför det *ser ut* som `git diff`:** två kosmetiska val härmar git-formatet —
`a/<path>` / `b/<path>`-filhuvuden och `@@`-hunkmarkörer. Färgläggningen
(`+`/`-` grönt/rött) kommer från Rich: `Syntax("\n".join(lines), "diff", …)` i
`_diff_syntax` (`chat_ui.py:1135`), inte från git. Sätts `NO_COLOR` faller den
tillbaka till ren text.

**Viktig konsekvens:** diffen jämför **det gamla innehållet i minnet mot det nya
innehållet** som verktyget skriver — inte mot git:s HEAD eller staging. Den är
alltså helt frikopplad från om filen är spårad i git, ostagead eller utanför
repo:t. Inga git-kommandon, ingen arbetskatalog-status, inget index läses.

**Detaljer värda att nämna:**

- **Trunkering:** diffen kapas vid `DIFF_MAX_LINES = 40` rader med en
  `... N more lines (full edit in trace)`-svans — hela ändringen ligger kvar i
  JSONL-tracen.
- **Tom-men-ändrad-fallback:** om `unified_diff` ger noll rader men `old != new`
  (t.ex. enradsfil utan radslut) byggs en minimal `---/+++/@@/-/+`-hunk för hand
  (`chat_ui.py:1121`).
- **Var den används:** samma `format_unified_diff` driver både den inline
  progress-strömmen (`render_progress_file_diff`) och "Changes"-panelerna i
  chatt-UI:t.

**Sammanfattning:** git-stil-*utseende*, stdlib-*motor*. Det är ett medvetet
val i linje med repos filosofi — litet, granskningsbart, inget externt
beroende och ingen koppling till repo-tillstånd.

## Vad händer om agenten eller jag gör `ssh`?

**Kort svar:** Agenten kan **inte** köra `ssh` — det blockeras alltid, före
exekvering. Om **du själv** kör `ssh` i din egen terminal gör den här koden
ingenting åt det; då är det bara din vanliga host-shell.

### Om agenten försöker köra `ssh`

`run_bash` är deny-by-default. Vid t.ex. `ssh user@host ls` slår två oberoende
spärrar till i `validate_shell_command` (`src/vg_agent/tools.py`):

1. **Inte i allowlistan** (`tools.py:273`) — `ssh` finns inte i `SAFE_COMMANDS`
   (bara `grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `head`, `tail`, `wc`).
   Returnerar `command 'ssh' is not in the read-only allowlist`.
2. **Destruktiv token** (`tools.py:23`, `:276`) — `ssh` står även explicit i
   `DESTRUCTIVE_TOKENS` tillsammans med `scp`, `rsync`, `nc`, `ncat`, `netcat`,
   `ftp`, `git`. Två oberoende grindar = ingen enskild lista att glömma.

Anropet når **aldrig** skalet. `run_bash` returnerar bara
`run_bash blocked: ...` (`tools.py:409`) som ett tool-error, och loopen
fortsätter. Testet `tests/test_vg_agent.py:669` låser fast detta:
`assert validate_shell_command("ssh user@host ls") is not None`.

Dessutom: även om ett kommando vore tillåtet kan agenten inte läsa SSH-nycklar
— alla `.ssh/`-sökvägar, `id_rsa`/`id_ed25519`, `.pem`, `.key` är blockerade som
sensitive paths (`tools.py:35–51`, regressionstest `tests/test_vg_agent.py:5400`).

### Om *du* kör `ssh`

Då går du utanför agenten. `validate_shell_command` gäller bara kommandon som
agenten skickar genom `run_bash`-verktyget — den hookar **inte** din interaktiva
terminal. Din `ssh` körs som vanligt med dina rättigheter.

Två nyanser värda att nämna:

- Kör du agenten i **Docker** (`docker compose run`) är containern ett yttre
  lager: utgående `ssh` därifrån begränsas av containerns nätverk/nycklar, inte
  av host-skalet. CLAUDE.md kallar Docker "an outer safety layer, not the only
  one" — den in-process-grinden är obligatorisk oavsett container.
- Vill du köra agenten *via* `ssh` till en annan maskin är det helt ok — det är
  transporten dit, inte något agenten gör.

**Sammanfattning:** Agentens egen `ssh` blockeras dubbelt (allowlist +
destruktiv-token-lista) och fångas av enhetstest. Din egen `ssh` är opåverkad —
grinden gäller bara verktygsanrop, inte din shell.

## Kan agenten nå resurser på nätverket?

**Kort svar:** Nej — agentens *verktyg* kan inte nå nätverket. All utgående
nätverkstrafik via `run_bash` blockeras före exekvering. Den **enda** nätverks-
trafik agenten gör är LLM-anropen själva (LiteLLM → OpenRouter), och det är
medvetet och oundvikligt — det är så modellerna körs.

### Verktygen kan inte nå nätet

Det finns inget nätverksverktyg i agentens verktygslåda. `read_file`,
`read_file_range`, `write_file`, `edit_file` rör **bara** filer under workspace-
roten (absoluta sökvägar och `..` avvisas). Det finns ingen `fetch_url`, ingen
`http`-klient, inget verktyg som tar en URL. Det enda sättet en agent ens skulle
kunna *försöka* nå nätet är via `run_bash`, och där slår tre oberoende grindar
till i `validate_shell_command` (`src/vg_agent/tools.py`):

1. **Allowlistan** (`tools.py:273`) — `run_bash` är deny-by-default. Bara lokala,
   read-only kommandon är tillåtna (`grep`, `rg`, `find`, `ls`, `pwd`, `cat`,
   `head`, `tail`, `wc`; plus `rm`/`mkdir` via approval-grinden). Inget av dem
   talar med nätet. Ett `curl https://…` returnerar
   `command 'curl' is not in the read-only allowlist`.
2. **Destruktiv-token-listan** (`tools.py:18`, `:276`) — `DESTRUCTIVE_TOKENS`
   innehåller dessutom explicit varenda vanlig nätverks-binär:
   `curl`, `wget`, `ssh`, `scp`, `sftp`, `rsync`, `ftp`, `telnet`, `nc`, `ncat`,
   `netcat`, `socat` (och `git`, `pip`, `npm`, `uv` m.fl. som annars kunde dra
   hem paket). Två oberoende listor = ingen enskild lista att glömma.
3. **Shell-control-grinden** (`tools.py:30`) — `;`, `&&`, `||`, `|`, `>`, `<`,
   backtick och `$(` avvisas alla. Det stänger kringgåenden som
   `cat > /dev/tcp/host/port` (bash:s inbyggda socket-trick) eller att kedja på
   ett dolt andra-kommando.

Anropet når **aldrig** skalet — `run_bash` returnerar bara
`run_bash blocked: …` som ett tool-error och loopen fortsätter.

### Den nätverkstrafik som *finns* (by design)

Agenten är inte offline. Varje modell-tur går via `live_model_client.py`
(LiteLLM-adapter) ut till **OpenRouter** — det är hela exekveringsvägen
(`run_live_task` är den enda runtime-vägen, och `--task` exit:ar `2` utan
`OPENROUTER_API_KEY`). Det är alltså rätt att säga: *agenten själv* pratar med
nätet, men bara med LLM-endpointen, aldrig med godtyckliga resurser som modellen
ber om. Nyckeln läses från env (`OPENROUTER_API_KEY`), aldrig committad.

### Docker som yttre lager

Kör du demon i Docker (`docker compose run`) är containern ett extra lager:
utgående trafik därifrån begränsas av containerns nätverk, inte av host-skalet.
CLAUDE.md kallar Docker "an outer safety layer, not the only one" — den
in-process-grinden ovan är obligatorisk oavsett container.

### Om *du* kör nätverkskommandon

Som med `ssh`: `validate_shell_command` hookar bara kommandon som agenten
skickar genom `run_bash`. Din egen interaktiva terminal är opåverkad — kör du
`curl`/`ssh` själv går det som vanligt med dina rättigheter.

**Sammanfattning:** Agentens verktyg är nät-isolerade — tre oberoende grindar
(allowlist, destruktiv-token-lista, shell-control) hindrar varje utgående
anrop, och det finns inget URL-verktyg överhuvudtaget. Den enda nätverkstrafik
agenten gör är LLM-anropen till OpenRouter via LiteLLM.
