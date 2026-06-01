Jag vill pitcha min VG-uppgift: Codesaver CLI by Spargeek.
En autonom, terminalbaserad kodassistent byggd för att konkurrera direkt med Claude Code och Codex, men med fokus på resurseffektivitet och delegering.

Dagens AI-assistenter tenderar att drabbas av "context bloat", där tool-outputs  snabbt äter upp context-fönstret, driver upp kostnader och dessutom gör agenten förvirrad. Codesaver löser detta genom smart orkestrering och aktiv context engineering.

Core Architecture & Features:
Multi-Agent Sub-Delegation: En central Main_Agent/Dirigent som analyserar användarens prompt och spawnar specialiserade, parallella sub-agenter ("Grilling", Explorer, Coder, Reviewer) för specifika uppdrag. Grilling ska vara en envis agent som ställer frågor för att få till en bättre plan/upplägg

Context Engineering (CW Trimming): För att skydda context window (CW) vill jag ha en automatisk tool-result compaction. Långa terminal-outputs eller filavläsningar komprimeras till semantiska sammanfattningar innan de injiceras i agentens historik, vilket sparar tokens och bibehåller fokus o 'main context'.

Destruktiva eller riskfyllda anrop blockeras eller kräver manuell override innan exekvering.

FinOPS Dashboard: Live-monitorering av token-konsumtion per agent/sub-agent med statistik för att på sikt åstadkomma bättre subagenter.