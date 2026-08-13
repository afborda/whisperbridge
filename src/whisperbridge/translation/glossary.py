import re

# Termos que nao devem ser traduzidos ou tem traducao especifica para tech/dados
GLOSSARY: dict[str, str] = {
    "dashboard": "dashboard",
    "dashboards": "dashboards",
    "deployment": "deploy",
    "deploy": "deploy",
    "pipeline": "pipeline",
    "data pipeline": "pipeline de dados",
    "pull request": "pull request",
    "pull requests": "pull requests",
    "code review": "code review",
    "sprint": "sprint",
    "backlog": "backlog",
    "stakeholder": "stakeholder",
    "stakeholders": "stakeholders",
    "roadmap": "roadmap",
    "feature flag": "feature flag",
    "feature flags": "feature flags",
    "rollback": "rollback",
    "hotfix": "hotfix",
    "on-call": "de plantão",
    "on call": "de plantão",
    "bug": "bug",
    "bugs": "bugs",
    "release": "release",
    "releases": "releases",
    "branch": "branch",
    "branches": "branches",
    "merge": "merge",
    "commit": "commit",
    "commits": "commits",
    "Databricks": "Databricks",
    "widget": "widget",
    "widgets": "widgets",
    "BFF": "BFF",
    "API": "API",
    "APIs": "APIs",
    "SQL": "SQL",
    "Kafka": "Kafka",
    "Spark": "Spark",
}

_pattern = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(GLOSSARY, key=len, reverse=True)) + r")\b",
    flags=re.IGNORECASE,
)


def apply_glossary(text: str) -> str:
    def replace(match: re.Match) -> str:
        original = match.group(0)
        key = next((k for k in GLOSSARY if k.lower() == original.lower()), None)
        return GLOSSARY[key] if key else original

    return _pattern.sub(replace, text)
