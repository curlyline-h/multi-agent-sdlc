# 🤖 Multi-Agent SDLC — Sistem autonom de dezvoltare a ciclului de viață al software-ului

> Un sistem AI puternic, complet autonom pentru dezvoltarea ciclului de viață al software-ului (SDLC) care primește o cerință în limbaj natural și orchestrează o echipă de agenți AI specializați pentru a planifica, proiecta, construi, revizui, testa, securiza și implementa o aplicație funcțională — de la început până la sfârșit, fără intervenție umană.

---

## 📋 Cuprins

1. [Prezentare generală](#prezentare-generală)
2. [Arhitectura sistemului](#arhitectura-sistemului)
3. [Structura proiectului](#structura-proiectului)
4. [Fluxul de lucru al agentului](#fluxul-de-lucru-al-agentului)
5. [Motorul de orchestrare](#motorul-de-orchestrare)
6. [API backend](#api-backend)
7. [Dashboard frontend](#dashboard-frontend)
8. [Flux de date & Managementul stării](#flux-de-date--managementul-stării)
9. [Tehnici de optimizare](#tehnici-de-optimizare)
10. [Stack tehnologic](#stack-tehnologic)
11. [Rularea sistemului](#rularea-sistemului)
12. [Variabile de mediu](#variabile-de-mediu)

---

## Prezentare generală

**Multi-Agent SDLC** este o platformă de dezvoltare autonomă de nivel producție. O utilizați astfel: oferiți o cerință precum "Construiește o aplicație de tip Bubble Shooter în React Native pentru Android" și sistemul:

1. Efectuează o **analiză de fezabilitate** și generează un PRD complet.
2. **Proiectează** arhitectura întregului sistem cu un stack tehnologic adecvat.
3. **Împarte** PRD‑ul în taskuri granular, conștiente de dependențe.
4. **Distribuie** taskurile agenților specializați (backend, frontend, QA etc.) în ordinea corectă.
5. Fiecare agent **scrie cod**, trece de linter și trimite un **Pull Request pe GitHub**.
6. Rulează un agent **Reviewer** pentru analiză statică, un agent **Security** pentru scanare de vulnerabilități și un agent **QA** pentru teste E2E.
7. Monitorizează totul în timp real printr-un **dashboard Next.js** cu loguri live, porți de aprobare și difuri.

---

## Variabile de mediu

Configurați sistemul editând fișierul `.env` de la rădăcina proiectului:

```env
# Configurare LLM
LLM_MODEL=llama3.2           # Orice model Ollama, sau numele modelului Groq
GROQ_API_KEY=                # Cheia API Groq (opțional)
OPENAI_API_KEY=              # Cheia API OpenAI (opțional)

# Integrare GitHub
GITHUB_TOKEN=                # Tokenul personal de acces GitHub (pentru crearea PR‑urilor)
GITHUB_USERNAME=             # Numele de utilizator GitHub

# Opțional
OLLAMA_BASE_URL=http://localhost:11434
```

> **Notă:** Fișierul `.env` este deja inclus în `.gitignore` și nu trebuie să fie împins în repository pentru a proteja secretele.

