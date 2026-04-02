import json
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "")

_github_available = bool(GITHUB_TOKEN)

if _github_available:
    try:
        from github import Github, GithubException, Auth
    except ImportError:
        _github_available = False


class GithubMCP:
    def __init__(self):
        self._client = None
        self._user = None

    def _get_client(self):
        if not _github_available:
            raise RuntimeError("PyGithub non disponible ou GITHUB_TOKEN manquant.")
        if self._client is None:
            self._client = Github(auth=Auth.Token(GITHUB_TOKEN))
            self._user = self._client.get_user()
        return self._client

    def _resolve_repo(self, repo: str):
        """Retourne l'objet repo PyGithub. Utilise GITHUB_DEFAULT_REPO si repo est vide."""
        client = self._get_client()
        target = repo if repo else GITHUB_DEFAULT_REPO
        if not target:
            raise ValueError("Aucun repo spécifié et GITHUB_DEFAULT_REPO non défini.")
        return client.get_repo(target)

    # ─── REPOS ───────────────────────────────────────────────────────────────

    def list_repos(self, limit: int = 20) -> str:
        """Liste les repos de l'utilisateur authentifié."""
        try:
            client = self._get_client()
            repos = list(self._user.get_repos()[:limit])
            if not repos:
                return "Aucun repo trouvé."
            lines = []
            for r in repos:
                visibility = "privé" if r.private else "public"
                lines.append(f"  - {r.full_name} | {visibility} | ⭐ {r.stargazers_count} | {r.language or 'N/A'}")
            return f"{len(repos)} repo(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur GitHub list_repos: {str(e)}"

    def get_repo_info(self, repo: str = "") -> str:
        """Informations détaillées sur un repo."""
        try:
            r = self._resolve_repo(repo)
            info = {
                "full_name": r.full_name,
                "description": r.description,
                "language": r.language,
                "stars": r.stargazers_count,
                "forks": r.forks_count,
                "open_issues": r.open_issues_count,
                "default_branch": r.default_branch,
                "private": r.private,
                "created_at": str(r.created_at),
                "updated_at": str(r.updated_at),
                "url": r.html_url,
                "topics": r.get_topics(),
            }
            return json.dumps(info, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur GitHub get_repo_info: {str(e)}"

    # ─── ISSUES ──────────────────────────────────────────────────────────────

    def list_issues(self, repo: str = "", state: str = "open", limit: int = 10) -> str:
        """Liste les issues d'un repo."""
        try:
            r = self._resolve_repo(repo)
            issues = list(r.get_issues(state=state)[:limit])
            if not issues:
                return f"Aucune issue ({state}) trouvée dans '{r.full_name}'."
            lines = []
            for i in issues:
                labels = ", ".join(l.name for l in i.labels) if i.labels else "—"
                lines.append(f"  #{i.number} | {i.title} | Labels: {labels} | {i.html_url}")
            return f"{len(issues)} issue(s) [{state}] dans {r.full_name} :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur GitHub list_issues: {str(e)}"

    def create_issue(self, title: str, body: str = "", labels=None, repo: str = "") -> str:
        """Crée une issue dans un repo."""
        try:
            r = self._resolve_repo(repo)
            kwargs = {"title": title}
            if body:
                kwargs["body"] = body
            if labels:
                label_list = labels if isinstance(labels, list) else [labels]
                kwargs["labels"] = label_list
            issue = r.create_issue(**kwargs)
            return f"Issue #{issue.number} créée : {issue.html_url}"
        except Exception as e:
            return f"Erreur GitHub create_issue: {str(e)}"

    # ─── PULL REQUESTS ───────────────────────────────────────────────────────

    def list_prs(self, repo: str = "", state: str = "open", limit: int = 10) -> str:
        """Liste les Pull Requests d'un repo."""
        try:
            r = self._resolve_repo(repo)
            prs = list(r.get_pulls(state=state)[:limit])
            if not prs:
                return f"Aucune PR ({state}) dans '{r.full_name}'."
            lines = []
            for pr in prs:
                lines.append(
                    f"  #{pr.number} | {pr.title} | {pr.head.ref} -> {pr.base.ref} | {pr.html_url}"
                )
            return f"{len(prs)} PR(s) [{state}] dans {r.full_name} :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur GitHub list_prs: {str(e)}"

    def get_pr(self, pr_number: int, repo: str = "") -> str:
        """Détail d'une Pull Request."""
        try:
            r = self._resolve_repo(repo)
            pr = r.get_pull(int(pr_number))
            info = {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "body": (pr.body or "")[:500],
                "author": pr.user.login,
                "base": pr.base.ref,
                "head": pr.head.ref,
                "mergeable": pr.mergeable,
                "merged": pr.merged,
                "commits": pr.commits,
                "changed_files": pr.changed_files,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "created_at": str(pr.created_at),
                "url": pr.html_url,
            }
            return json.dumps(info, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur GitHub get_pr: {str(e)}"

    # ─── COMMITS ─────────────────────────────────────────────────────────────

    def list_commits(self, repo: str = "", branch: str = "main", limit: int = 10) -> str:
        """Liste les derniers commits d'une branche."""
        try:
            r = self._resolve_repo(repo)
            commits = list(r.get_commits(sha=branch)[:limit])
            if not commits:
                return f"Aucun commit trouvé sur la branche '{branch}'."
            lines = []
            for c in commits:
                author = c.commit.author.name if c.commit.author else "?"
                date = str(c.commit.author.date) if c.commit.author else "?"
                msg = c.commit.message.split("\n")[0][:80]
                lines.append(f"  {c.sha[:7]} | {author} | {date} | {msg}")
            return f"{len(commits)} commit(s) sur '{branch}' dans {r.full_name} :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur GitHub list_commits: {str(e)}"

    # ─── CODE SEARCH ─────────────────────────────────────────────────────────

    def search_code(self, query: str, repo: str = "") -> str:
        """Recherche dans le code source d'un repo via l'API GitHub Search."""
        try:
            client = self._get_client()
            target = repo if repo else GITHUB_DEFAULT_REPO
            search_query = f"{query} repo:{target}" if target else query
            results = list(client.search_code(search_query)[:10])
            if not results:
                return f"Aucun résultat pour '{query}'."
            lines = []
            for r in results:
                lines.append(f"  - {r.path} | {r.html_url}")
            return f"{len(results)} résultat(s) pour '{query}' :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur GitHub search_code: {str(e)}"
