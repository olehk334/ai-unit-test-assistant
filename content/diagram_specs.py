"""Diagrams of the PDP document: three columns, one row per step, EN and RU labels."""


def T(en, ru=None):
    return {"en": en, "ru": ru if ru is not None else en}


def C(title, sub):
    return (title, sub)


ONE_PR = {
    "id": "one-pr",
    "caption": T(
        "One pull request, from changed code to reviewed tests.",
        "Один pull request: от изменённого кода до проверенных тестов.",
    ),
    "columns": [T("Developer", "Разработчик"), T("Assistant", "Ассистент"), T("Result", "Результат")],
    "seq_col": 1,
    "rows": [
        {0: C(T("Changes Python code", "Меняет Python-код"), T("opens a pull request", "открывает pull request")),
         1: C(T("Finds what changed", "Находит, что изменилось"), T("git diff, public functions", "git diff, публичные функции")),
         2: C(T("A list of targets", "Список целей"), T("functions that need tests", "функции, которым нужны тесты"))},
        {0: C(T("Waits", "Ждёт"), T("a few minutes", "несколько минут")),
         1: C(T("Asks Gemini for tests", "Просит у Gemini тесты"), T("one prompt per changed file", "один промпт на файл")),
         2: C(T("A pytest module", "Модуль pytest"), T("validated before it is saved", "проверен до сохранения"))},
        {0: C(T("Waits", "Ждёт"), T("")),
         1: C(T("Runs the tests", "Запускает тесты"), T("fixes failures, up to 2 times", "чинит падения, до 2 раз")),
         2: C(T("passed / failed"), T("per changed file", "по каждому файлу"))},
        {0: C(T("Opens the report", "Открывает отчёт"), T("in the PR run summary", "в summary запуска PR")),
         1: C(T("Writes the report", "Пишет отчёт"), T("Markdown + JSON")),
         2: C(T("Tests + suggestions", "Тесты + предложения"), T("as artifacts, nothing committed", "артефакты, ничего не закоммичено"))},
        {"dashed": 0,
         0: C(T("Reviews and decides", "Смотрит и решает"), T("keep, edit or drop", "оставить, поправить, выбросить")),
         1: C(T("Does nothing by itself", "Сам ничего не делает"), T("no auto-commit, no overwrite", "без автокоммита и перезаписи")),
         2: C(T("Better tests, same control", "Тесты лучше, контроль ваш"), T("the human stays in charge", "решение остаётся за человеком"))},
    ],
    "footer": T(
        "Dashed box: done by a person. Everything else runs by itself.",
        "Пунктир — делает человек. Всё остальное работает само.",
    ),
}

CORE_STEPS = {
    "id": "core",
    "caption": T(
        "Inside the assistant: eight steps, one module each, called in this order by pipeline.py.",
        "Внутри ассистента: восемь шагов, у каждого свой модуль, pipeline.py вызывает их по порядку.",
    ),
    "columns": [T("Question", "Вопрос"), T("Module", "Модуль"), T("Output", "Результат")],
    "seq_col": 1,
    "rows": [
        {0: C(T("What changed?", "Что изменилось?"), T("git diff base...HEAD")),
         1: C(T("changed_files.py"), T("production .py files only", "только прод-код .py")),
         2: C(T("Files + changed lines", "Файлы + номера строк"), T(""))},
        {0: C(T("In which order?", "В каком порядке?"), T("imports between changed files", "импорты между файлами")),
         1: C(T("import_graph.py"), T("Kahn's topological sort", "топологическая сортировка Кана")),
         2: C(T("Dependencies first", "Сначала зависимости"), T("import cycles listed", "циклы попадают в отчёт"))},
        {0: C(T("What needs tests?", "Что тестировать?"), T("public code the diff touched", "публичный код в диффе")),
         1: C(T("test_targets.py"), T("AST only, nothing is executed", "только AST, код не исполняется")),
         2: C(T("Test targets", "Цели для тестов"), T("functions and methods", "функции и методы"))},
        {0: C(T("What tests exist?", "Какие тесты уже есть?"), T("under tests/", "в папке tests/")),
         1: C(T("test_finder.py"), T("name match + references", "по имени + по ссылкам")),
         2: C(T("Related test files", "Связанные тесты"), T("context for the prompt", "контекст для промпта"))},
        {0: C(T("Ask Gemini", "Запрос к Gemini"), T("temperature 0")),
         1: C(T("llm_client.py · prompts.py"), T("response cache: LRU / LFU", "кэш ответов: LRU / LFU")),
         2: C(T("Test module text", "Текст тест-модуля"), T("a cache hit costs 0 tokens", "попадание в кэш — 0 токенов"))},
        {0: C(T("Do the tests pass?", "Тесты проходят?"), T("run, fix, run again", "запуск, починка, запуск")),
         1: C(T("test_generator.py"), T("validate → pytest → repair ≤ 2", "проверка → pytest → починка ≤ 2")),
         2: C(T("passed / failed"), T("tests/generated/…"))},
        {0: C(T("Old tests outdated?", "Старые тесты устарели?"), T("related tests from step 4", "связанные тесты из шага 4")),
         1: C(T("suggested_updates.py"), T("full new version, original kept", "новая версия, оригинал цел")),
         2: C(T("Suggested updates", "Предложенные правки"), T("reports/suggested-tests/"))},
        {0: C(T("What happened?", "Что получилось?"), T("one entry per file", "по записи на файл")),
         1: C(T("report.py"), T("Markdown + JSON")),
         2: C(T("ai-test-report.md"), T("+ .json for machines", "+ .json для машин"))},
    ],
    "footer": T(
        "pipeline.py calls these eight steps in this order and holds no other logic.",
        "pipeline.py вызывает эти восемь шагов по порядку, другой логики в нём нет.",
    ),
}

TWO_WAYS = {
    "id": "two-ways",
    "caption": T(
        "The same core runs in three places. Only the trigger and the delivery differ.",
        "Одно и то же ядро работает в трёх местах. Различаются только запуск и доставка результата.",
    ),
    "columns": [T("Trigger", "Запуск"), T("Where it runs", "Где работает"), T("Result goes to", "Куда уходит результат")],
    "seq_col": None,
    "rows": [
        {0: C(T("PR in GitHub", "PR в GitHub"), T("any Python file changed", "изменён любой Python-файл")),
         1: C(T("GitHub Actions", "GitHub Actions"), T("ai-test-assistant.yml · CLI mode", "ai-test-assistant.yml · режим CLI")),
         2: C(T("Run summary + artifacts", "Summary + артефакты"), T("report, tests, suggestions", "отчёт, тесты, предложения"))},
        {0: C(T("Webhook from GitHub", "Webhook от GitHub"), T("PR opened or updated", "PR открыт или обновлён")),
         1: C(T("Google Cloud", "Google Cloud"), T("receiver → Pub/Sub → worker", "ресивер → Pub/Sub → воркер")),
         2: C(T("Cloud Storage + PR status", "Cloud Storage + статус PR"), T("✓ / ✗ on the commit", "✓ / ✗ на коммите"))},
        {0: C(T("Your terminal", "Ваш терминал"), T("ai-test-assistant …")),
         1: C(T("Your machine", "Ваш компьютер"), T("--dry-run needs no cloud", "--dry-run без облака")),
         2: C(T("reports/ and tests/generated/"), T("in the repository folder", "в папке репозитория"))},
    ],
}

CI_FLOW = {
    "id": "ci",
    "caption": T(
        "What happens in GitHub Actions when a pull request changes Python code.",
        "Что происходит в GitHub Actions, когда pull request меняет Python-код.",
    ),
    "columns": [T("GitHub event", "Событие GitHub"), T("Workflow step", "Шаг workflow"), T("What you see", "Что вы видите")],
    "seq_col": 1,
    "rows": [
        {0: C(T("Pull request opened", "Pull request открыт"), T("paths: **/*.py")),
         1: C(T("Checkout, full history", "Checkout, вся история"), T("fetch-depth: 0 for git diff", "fetch-depth: 0 для git diff")),
         2: C(T("Job starts", "Задача стартует"), T("in the Checks tab", "во вкладке Checks"))},
        {0: C(T("Secrets provided", "Секреты выданы"), T("project, location, model", "проект, регион, модель")),
         1: C(T("pip install -e \".[dev]\""), T("Python 3.12")),
         2: C(T("Nothing yet", "Пока ничего"), T("≈1 minute", "≈1 минута"))},
        {0: C(T("—"), T("")),
         1: C(T("run-pr-assistant"), T("--base-ref origin/<base>")),
         2: C(T("Generated tests", "Сгенерированные тесты"), T("in the job log", "в логе задачи"))},
        {0: C(T("—"), T("")),
         1: C(T("Report → step summary", "Отчёт → summary шага"), T("if: always()")),
         2: C(T("Report on the run page", "Отчёт на странице запуска"), T("even when a step failed", "даже если шаг упал"))},
        {0: C(T("—"), T("")),
         1: C(T("Upload artifacts", "Загрузить артефакты"), T("tests/generated/ · reports/")),
         2: C(T("Downloadable zip", "Zip для скачивания"), T("nothing is committed", "ничего не коммитится"))},
        {"dashed": 0,
         0: C(T("Label: apply-ai-suggestions", "Метка: apply-ai-suggestions"), T("set by a maintainer", "ставит мейнтейнер")),
         1: C(T("apply-suggestions"), T("second workflow, demo repo", "второй workflow, демо-репо")),
         2: C(T("Commit on the PR branch", "Коммит в ветку PR"), T("only after a human asked", "только по просьбе человека"))},
    ],
    "footer": T(
        "Dashed box: a person decides. Everything else runs on every pull request.",
        "Пунктир — решает человек. Всё остальное выполняется на каждом pull request.",
    ),
}

TEST_BIRTH = {
    "id": "test-birth",
    "caption": T(
        "How a generated test earns its place: every answer is checked before it is trusted.",
        "Как сгенерированный тест заслуживает место: каждый ответ проверяется, прежде чем ему поверят.",
    ),
    "columns": [T("LLM answer", "Ответ LLM"), T("Check", "Проверка"), T("Outcome", "Исход")],
    "seq_col": 1,
    "rows": [
        {0: C(T("Raw text", "Сырой текст"), T("may contain ``` fences", "может содержать ``` ограждения")),
         1: C(T("Clean", "Очистка"), T("strip Markdown fences", "убрать Markdown-ограждения")),
         2: C(T("Plain Python text", "Чистый текст Python"), T(""))},
        {0: C(T("—"), T("")),
         1: C(T("Validate", "Проверка"), T("parses · has test_ · no shell", "парсится · есть test_ · не shell")),
         2: C(T("ValidationError → status error", "ValidationError → статус error"), T("nothing is written", "ничего не записывается"))},
        {0: C(T("—"), T("")),
         1: C(T("Write with a header", "Запись с заголовком"), T("tests/generated/test_…_generated.py")),
         2: C(T("A file reviewers can read", "Файл для ревью"), T("marked as AI-generated", "помечен как сгенерированный"))},
        {0: C(T("—"), T("")),
         1: C(T("Run pytest", "Запуск pytest"), T("subprocess, 120 s timeout", "подпроцесс, таймаут 120 с")),
         2: C(T("passed → done", "passed → готово"), T(""))},
        {0: C(T("Failure output", "Вывод падения"), T("pytest stdout + stderr")),
         1: C(T("Repair prompt", "Промпт на починку"), T("source + test + failure", "исходник + тест + ошибка")),
         2: C(T("New answer → same checks", "Новый ответ → проверки"), T("at most 2 repairs", "не больше 2 починок"))},
        {0: C(T("—"), T("")),
         1: C(T("Give up after 2", "Остановка после 2"), T("status failed, file kept", "статус failed, файл остаётся")),
         2: C(T("Report says why", "Отчёт говорит почему"), T("the reviewer sees the failure", "ревьюер видит падение"))},
    ],
}

LLM_CALL = {
    "id": "llm-call",
    "caption": T(
        "One call to Gemini: what goes in, what controls the answer, what comes out.",
        "Один вызов Gemini: что входит, что управляет ответом, что выходит.",
    ),
    "columns": [T("What goes in", "Что входит"), T("What controls it", "Что управляет"), T("What comes out", "Что выходит")],
    "seq_col": None,
    "rows": [
        {0: C(T("System instruction", "Системная инструкция"), T("rules: pytest only, no prose", "правила: только pytest, без прозы")),
         1: C(T("Three fixed prompts", "Три фиксированных промпта"), T("generate · repair · update", "генерация · починка · обновление")),
         2: C(T("Python text", "Текст на Python"), T("validated before use", "проверяется перед использованием"))},
        {0: C(T("Full source + targets", "Весь исходник + цели"), T("module path, not disk path", "путь модуля, не путь на диске")),
         1: C(T("temperature = 0"), T("same input → same answer", "тот же вход → тот же ответ")),
         2: C(T("Deterministic output", "Детерминированный вывод"), T("cacheable, reproducible", "кэшируемый, воспроизводимый"))},
        {0: C(T("Related tests", "Связанные тесты"), T("style and fixtures to follow", "стиль и фикстуры для подражания")),
         1: C(T("Cache key = SHA-256", "Ключ кэша = SHA-256"), T("model + temperature + prompts", "модель + температура + промпты")),
         2: C(T("Repeat prompt: 0 tokens", "Повтор промпта: 0 токенов"), T("served from LRU / LFU", "из кэша LRU / LFU"))},
        {0: C(T("Credentials", "Учётные данные"), T("ADC, no keys in code", "ADC, без ключей в коде")),
         1: C(T("Vertex AI client", "Клиент Vertex AI"), T("google-genai, created lazily", "google-genai, создаётся лениво")),
         2: C(T("Usage counters", "Счётчики использования"), T("calls, seconds, tokens", "вызовы, секунды, токены"))},
        {0: C(T("--dry-run"), T("no cloud at all", "вообще без облака")),
         1: C(T("Fixed placeholder test", "Фиксированный тест-заглушка"), T("same code path, no network", "тот же путь кода, без сети")),
         2: C(T("Free, offline CI", "Бесплатный офлайн CI"), T("103 tests run this way", "103 теста работают так"))},
    ],
}

PLATFORM_FLOW = {
    "id": "platform",
    "caption": T(
        "The cloud mode, end to end. Row 4 is the same core the CLI runs.",
        "Облачный режим от начала до конца. Строка 4 — то же ядро, что запускает CLI.",
    ),
    "columns": [T("GitHub"), T("Google Cloud"), T("Result", "Результат")],
    "seq_col": 1,
    "rows": [
        {0: C(T("PR opened or pushed", "PR открыт или обновлён"), T("signed webhook (HMAC)", "подписанный webhook (HMAC)")),
         1: C(T("webhook-receiver"), T("Cloud Run · public", "Cloud Run · публичный")),
         2: C(T("202 queued", "202 — в очереди"), T("401 on a bad signature", "401 при плохой подписи"))},
        {0: C(T("Job {repo, pr, sha}", "Задача {repo, pr, sha}"), T("JSON message", "JSON-сообщение")),
         1: C(T("Pub/Sub topic", "Топик Pub/Sub"), T("at-least-once · 5 attempts", "at-least-once · 5 попыток")),
         2: C(T("Dead-letter topic", "Dead-letter топик"), T("after the 5th failure", "после 5-й неудачи"))},
        {0: C(T("Push delivery", "Push-доставка"), T("POST /pubsub")),
         1: C(T("analysis-worker"), T("Cloud Run · private · 1 job", "Cloud Run · приватный · 1 задача")),
         2: C(T("Skipped if already done", "Пропуск, если уже сделано"), T("report already in GCS", "отчёт уже лежит в GCS"))},
        {0: C(T("Clone the PR head", "Клонировать голову PR"), T("git clone + checkout sha")),
         1: C(T("Core pipeline", "Ядро (pipeline)"), T("same library as the CLI", "та же библиотека, что в CLI")),
         2: C(T("Tests + report", "Тесты + отчёт"), T("per changed file", "по каждому изменённому файлу"))},
        {0: C(T("Upload artifacts", "Загрузить артефакты"), T("reports/ · tests/generated/")),
         1: C(T("Cloud Storage"), T("repo/pr/sha/…")),
         2: C(T("Artifact link", "Ссылка на артефакты"), T("the path is the idempotency key", "путь — ключ идемпотентности"))},
        {0: C(T("Post the result", "Опубликовать результат"), T("commit status", "статус коммита")),
         1: C(T("GitHub Statuses API"), T("best effort")),
         2: C(T("✓ / ✗ on the PR", "✓ / ✗ в PR"), T("context: ai-test-assistant"))},
        {"dashed": 1,
         0: C(T("Developer", "Разработчик"), T("opens the result", "открывает результат")),
         1: C(T("Manual review", "Ручное ревью"), T("keep the useful tests", "оставить полезные тесты")),
         2: C(T("A human decides", "Решает человек"), T(""))},
    ],
    "footer": T(
        "Dashed box: done by people. Everything else runs by itself.",
        "Пунктир — делают люди. Всё остальное работает само.",
    ),
}

METRICS_FLOW = {
    "id": "metrics",
    "caption": T(
        "From an event in the worker to a number on the dashboard.",
        "От события в воркере до числа на дашборде.",
    ),
    "columns": [T("Event in the worker", "Событие в воркере"), T("Metric", "Метрика"), T("On the dashboard", "На дашборде")],
    "seq_col": None,
    "rows": [
        {0: C(T("A job finishes", "Задача завершилась"), T("processed / failed / skipped")),
         1: C(T("jobs_processed_total{status}"), T("counter: only goes up", "счётчик: только растёт")),
         2: C(T("Jobs per minute", "Задач в минуту"), T("rate(…[5m]) * 60"))},
        {0: C(T("A job takes time", "Задача длится"), T("clone + LLM + pytest")),
         1: C(T("job_duration_seconds"), T("histogram: 7 buckets", "гистограмма: 7 корзин")),
         2: C(T("p50 / p95 duration", "Длительность p50 / p95"), T("histogram_quantile"))},
        {0: C(T("Gemini answers", "Gemini отвечает"), T("or the cache does", "или отвечает кэш")),
         1: C(T("llm_calls_total · tokens"), T("counters", "счётчики")),
         2: C(T("Cost per minute", "Стоимость в минуту"), T("tokens → money", "токены → деньги"))},
        {0: C(T("Cache lookup", "Обращение к кэшу"), T("hit or miss", "попадание или промах")),
         1: C(T("llm_cache_hits_total{policy}"), T("+ misses, per policy", "+ промахи, по политике")),
         2: C(T("Hit ratio", "Доля попаданий"), T("lru vs lfu side by side", "lru и lfu рядом"))},
        {0: C(T("A test file passes or not", "Тест-файл прошёл или нет"), T("after repairs", "после починок")),
         1: C(T("generated_test_files_total{result}"), T("counter", "счётчик")),
         2: C(T("Pass ratio", "Доля прошедших"), T("the quality KPI", "главный KPI качества"))},
        {0: C(T("Prometheus asks", "Prometheus спрашивает"), T("every 5 seconds", "каждые 5 секунд")),
         1: C(T("GET /metrics"), T("text format, pull model", "текстовый формат, pull-модель")),
         2: C(T("Alerts", "Алерты"), T(">20% failing · p95 > 5 min", ">20% ошибок · p95 > 5 мин"))},
    ],
}

ALGORITHMS = {
    "id": "algorithms",
    "caption": T(
        "Two algorithms implemented from scratch, each solving a real problem of the pipeline.",
        "Два алгоритма, написанных с нуля, каждый решает реальную задачу пайплайна.",
    ),
    "columns": [T("Problem", "Задача"), T("Algorithm", "Алгоритм"), T("What it gives", "Что даёт")],
    "seq_col": None,
    "rows": [
        {0: C(T("Files depend on each other", "Зависимости между файлами"), T("service.py imports models.py", "service.py импортирует models.py")),
         1: C(T("Kahn's topological sort", "Топосортировка Кана"), T("import_graph.py · min-heap")),
         2: C(T("Dependencies first", "Сначала зависимости"), T("reproducible order", "воспроизводимый порядок"))},
        {0: C(T("Imports form a cycle", "Импорты образуют цикл"), T("a imports b, b imports a", "a импортирует b, b — a")),
         1: C(T("Leftover nodes = cycle", "Остаток = цикл"), T("no extra bookkeeping", "без лишнего учёта")),
         2: C(T("Reported, not fatal", "В отчёт, не ошибка"), T("original order kept", "исходный порядок сохранён"))},
        {0: C(T("Same prompt again", "Тот же промпт снова"), T("a re-pushed branch", "ветка отправлена заново")),
         1: C(T("LRU cache", "LRU-кэш"), T("dict + doubly linked list", "dict + двусвязный список")),
         2: C(T("0 tokens for a repeat", "0 токенов за повтор"), T("get and put in O(1)", "get и put за O(1)"))},
        {0: C(T("A few hot modules", "Несколько горячих модулей"), T("appear in most PRs", "в большинстве PR")),
         1: C(T("LFU cache", "LFU-кэш"), T("frequency buckets + min pointer", "корзины частот + min-указатель")),
         2: C(T("Popular entries survive", "Частые записи выживают"), T("LLM_CACHE_POLICY=lfu"))},
        {0: C(T("Which policy is better?", "Какая политика лучше?"), T("depends on the workload", "зависит от нагрузки")),
         1: C(T("Same jobs, both policies", "Одни задачи, обе политики"), T("counters carry a policy label", "у счётчиков метка policy")),
         2: C(T("Measured on the dashboard", "Измерено на дашборде"), T("not argued in words", "а не доказано словами"))},
    ],
}

PHASES = {
    "id": "phases",
    "caption": T(
        "How the project was built: in phases, each one checked before the next.",
        "Как строился проект: по фазам, каждая проверялась до следующей.",
    ),
    "columns": [T("Phase", "Фаза"), T("What was built", "Что сделано"), T("How it was checked", "Как проверено")],
    "seq_col": 0,
    "rows": [
        {0: C(T("1 · MVP", "1 · MVP"), T("May – June 2026", "май – июнь 2026")),
         1: C(T("CLI + GitHub Actions", "CLI + GitHub Actions"), T("generate, repair, suggest, report", "генерация, починка, отчёт")),
         2: C(T("Unit tests + dry-run CI", "Юнит-тесты + dry-run CI"), T("no cloud cost", "без затрат на облако"))},
        {0: C(T("2 · Cloud", "2 · Облако"), T("July 2026", "июль 2026")),
         1: C(T("Receiver, Pub/Sub, worker", "Ресивер, Pub/Sub, воркер"), T("deploy.sh for GCP", "deploy.sh для GCP")),
         2: C(T("Service tests", "Тесты сервисов"), T("signature, ack, retry", "подпись, ack, повтор"))},
        {0: C(T("3 · Monitoring", "3 · Мониторинг"), T("July 2026", "июль 2026")),
         1: C(T("Metrics, dashboard, alerts", "Метрики, дашборд, алерты"), T("docker-compose demo", "демо на docker-compose")),
         2: C(T("Counters on /metrics", "Счётчики на /metrics"), T("seen in Grafana", "видны в Grafana"))},
        {0: C(T("4 · Algorithms", "4 · Алгоритмы"), T("July 2026", "июль 2026")),
         1: C(T("Import order, LRU / LFU", "Порядок импортов, LRU / LFU"), T("from scratch", "с нуля")),
         2: C(T("Unit tests per algorithm", "Юнит-тесты на алгоритм"), T("cycles, evictions", "циклы, вытеснения"))},
        {0: C(T("5 · Simplification", "5 · Упрощение"), T("October 2026", "октябрь 2026")),
         1: C(T("15 small pull requests", "15 маленьких pull request"), T("one job per module, no async", "модуль — одна задача, без async")),
         2: C(T("Tests green after each", "Тесты зелёные после PR"), T("77 → 103 tests", "77 → 103 теста"))},
        {0: C(T("6 · Verification", "6 · Проверка"), T("October 2026", "октябрь 2026")),
         1: C(T("Everything run locally", "Всё запущено локально"), T("Docker, Pub/Sub emulator", "Docker, эмулятор Pub/Sub")),
         2: C(T("5 bugs found and fixed", "5 багов исправлено"), T("each with a failing test first", "к каждому сначала падающий тест"))},
    ],
}

PDP_COVERAGE = {
    "id": "pdp",
    "caption": T(
        "Every PDP topic keeps a working example in the code and a way to show it live.",
        "У каждой темы PDP есть рабочий пример в коде и способ показать его вживую.",
    ),
    "columns": [T("PDP topic", "Тема PDP"), T("Example in this project", "Пример в проекте"), T("How to show it", "Как показать")],
    "seq_col": None,
    "rows": [
        {0: C(T("AI tools for productivity", "AI для продуктивности"), T("Soft 1")),
         1: C(T("The assistant itself", "Сам ассистент"), T("tests from a diff in minutes", "тесты из диффа за минуты")),
         2: C(T("A PR run", "Запуск на PR"), T("report in the summary", "отчёт в summary"))},
        {0: C(T("CI/CD + coding agents", "CI/CD + coding agents"), T("Tech 2")),
         1: C(T("Two workflows + label flow", "Два workflow + метка"), T("ai-test-assistant.yml · ci.yml")),
         2: C(T("Actions tab", "Вкладка Actions"), T("artifacts, step summary", "артефакты, summary шага"))},
        {0: C(T("Unit test automation", "Автоматизация unit-тестов"), T("Tech 3")),
         1: C(T("Generate → validate → repair", "Генерация → проверка → fix"), T("test_generator.py")),
         2: C(T("tests/generated/"), T("+ suggested updates", "+ предложенные правки"))},
        {0: C(T("LLM development basics", "Основы LLM-разработки"), T("Tech 5")),
         1: C(T("Prompts, temperature 0, cache", "Промпты, temperature 0, кэш"), T("llm_client.py · prompts.py")),
         2: C(T("--dry-run vs real run", "--dry-run и реальный запуск"), T("token counters", "счётчики токенов"))},
        {0: C(T("Distributed systems & cloud", "Распределённые системы"), T("PDP 6")),
         1: C(T("receiver → Pub/Sub → worker"), T("idempotent, retried, dead-lettered", "идемпотентно, повторы, DLQ")),
         2: C(T("Emulator run or deploy.sh", "Эмулятор или deploy.sh"), T("poison job → dead letter", "битая задача → dead letter"))},
        {0: C(T("Monitoring", "Мониторинг"), T("PDP 7")),
         1: C(T("/metrics, dashboard, alerts", "/metrics, дашборд, алерты"), T("monitoring/")),
         2: C(T("docker compose up"), T("Grafana on :3000", "Grafana на :3000"))},
        {0: C(T("Topological sort, LRU / LFU", "Топосортировка, LRU / LFU"), T("PDP 8")),
         1: C(T("import_graph.py · cache.py"), T("from scratch, O(1) caches", "с нуля, кэши за O(1)")),
         2: C(T("Report order, hit ratio", "Порядок в отчёте, hit ratio"), T("LLM_CACHE_POLICY=lfu"))},
        {0: C(T("Time management", "Тайм-менеджмент"), T("Soft")),
         1: C(T("Scope cuts, phases, small PRs", "Срез scope, фазы, по одному PR"), T("")),
         2: C(T("Git history", "История git"), T("15 PRs, 103 tests", "15 PR, 103 теста"))},
    ],
}

ALL = [ONE_PR, CORE_STEPS, TWO_WAYS, CI_FLOW, TEST_BIRTH, LLM_CALL, PLATFORM_FLOW, METRICS_FLOW, ALGORITHMS, PHASES, PDP_COVERAGE]
