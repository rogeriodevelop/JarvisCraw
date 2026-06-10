"""Obsidian Vault integration for J.A.R.V.I.S. persistent memory.

Reads and writes Markdown notes to an Obsidian vault, enabling long-term
memory, session logging, and cross-project knowledge linking.
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class ObsidianBridge:
    """Bridge between J.A.R.V.I.S. agent and an Obsidian vault."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.jarvis_dir = self.vault_path / "JARVIS"
        self.sessions_dir = self.jarvis_dir / "sessions"
        self.projects_dir = self.jarvis_dir / "projects"
        self.decisions_dir = self.jarvis_dir / "decisions"
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create the JARVIS directory structure in the vault."""
        for d in [self.jarvis_dir, self.sessions_dir, self.projects_dir, self.decisions_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Create index note if it doesn't exist
        index_path = self.jarvis_dir / "JARVIS Index.md"
        if not index_path.exists():
            index_path.write_text(
                "---\n"
                "tags: [jarvis, index]\n"
                f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
                "---\n\n"
                "# J.A.R.V.I.S. — Índice do Cérebro\n\n"
                "Este vault contém toda a memória persistente do J.A.R.V.I.S.\n\n"
                "## Estrutura\n"
                "- [[sessions/]] — Logs de sessões de trabalho\n"
                "- [[projects/]] — Notas por projeto\n"
                "- [[decisions/]] — Decisões técnicas registradas\n",
                encoding="utf-8",
            )

    # ── Core Memory Operations ────────────────────────────────

    def remember(self, content: str, category: str = "general", tags: Optional[List[str]] = None, project: Optional[str] = None) -> str:
        """Save a memory note to the vault.

        Args:
            content: The information to remember (Markdown supported).
            category: One of 'session', 'project', 'decision', 'general'.
            tags: Optional list of tags for the note.
            project: Optional project name to link.

        Returns:
            Path of the created note (relative to vault).
        """
        tags = tags or []
        tags.insert(0, "jarvis")
        if category not in tags:
            tags.append(category)
        if project and project not in tags:
            tags.append(project.lower().replace(" ", "-"))

        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H-%M-%S")

        # Determine target directory
        dir_map = {
            "session": self.sessions_dir,
            "project": self.projects_dir,
            "decision": self.decisions_dir,
        }
        target_dir = dir_map.get(category, self.jarvis_dir)

        # Generate filename
        title_slug = re.sub(r"[^\w\s-]", "", content[:50]).strip().replace(" ", "-")[:40]
        filename = f"{date_str}_{time_str}_{title_slug}.md"
        filepath = target_dir / filename

        # Build frontmatter
        frontmatter = (
            "---\n"
            f"tags: [{', '.join(tags)}]\n"
            f"date: {date_str}\n"
            f"time: {timestamp.strftime('%H:%M:%S')}\n"
            f"category: {category}\n"
        )
        if project:
            frontmatter += f"project: {project}\n"
        frontmatter += "---\n\n"

        # Build note content
        note = frontmatter + content

        filepath.write_text(note, encoding="utf-8")

        # Update project note if applicable
        if project:
            self._update_project_note(project, filepath.name, content[:100])

        rel_path = str(filepath.relative_to(self.vault_path))
        return f"Memória salva com sucesso: {rel_path}"

    def recall(self, query: str, limit: int = 5) -> str:
        """Search memories by query (searches titles, content, and tags).

        Args:
            query: Search term.
            limit: Maximum number of results.

        Returns:
            Formatted string with matching memories.
        """
        query_lower = query.lower()
        results = []

        for md_file in self.jarvis_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                # Score based on matches
                score = 0
                name_lower = md_file.stem.lower()

                if query_lower in name_lower:
                    score += 3
                if query_lower in content.lower():
                    score += 1
                    # Bonus for tag matches
                    if f"tags:" in content and query_lower in content.split("---")[1].lower() if "---" in content else False:
                        score += 2

                if score > 0:
                    # Extract a preview
                    lines = content.split("\n")
                    # Skip frontmatter
                    body_start = 0
                    if lines[0].strip() == "---":
                        for i, line in enumerate(lines[1:], 1):
                            if line.strip() == "---":
                                body_start = i + 1
                                break

                    body = "\n".join(lines[body_start:]).strip()
                    preview = body[:200] + ("..." if len(body) > 200 else "")

                    results.append({
                        "file": str(md_file.relative_to(self.vault_path)),
                        "score": score,
                        "preview": preview,
                        "date": self._extract_date(content),
                    })
            except Exception:
                continue

        # Sort by score descending
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:limit]

        if not results:
            return f"Nenhuma memória encontrada para '{query}'."

        output = f"## Memórias encontradas para '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"### {i}. {r['file']}\n"
            output += f"📅 {r['date'] or 'Data desconhecida'}\n\n"
            output += f"{r['preview']}\n\n---\n\n"

        return output

    def search_memory(self, query: str) -> str:
        """Alias for recall with higher limit — for broader searches."""
        return self.recall(query, limit=10)

    # ── Session Management ────────────────────────────────────

    def save_session(self, project: str, summary: str, decisions: Optional[List[str]] = None, files_modified: Optional[List[str]] = None) -> str:
        """Save a complete session summary.

        Args:
            project: Project name.
            summary: Session summary text.
            decisions: List of decisions made.
            files_modified: List of files changed.

        Returns:
            Path of the session note.
        """
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H:%M")

        filename = f"{date_str}_{project.replace(' ', '-')}.md"
        filepath = self.sessions_dir / filename

        content = (
            "---\n"
            f"tags: [jarvis, session, {project.lower().replace(' ', '-')}]\n"
            f"date: {date_str}\n"
            f"project: {project}\n"
            "type: session\n"
            "---\n\n"
            f"# Sessão {project} — {date_str} {time_str}\n\n"
            f"## Resumo\n{summary}\n\n"
        )

        if decisions:
            content += "## Decisões Tomadas\n"
            for d in decisions:
                content += f"- {d}\n"
            content += "\n"

        if files_modified:
            content += "## Arquivos Modificados\n"
            for f in files_modified:
                content += f"- `{f}`\n"
            content += "\n"

        content += f"## Links\n- [[{project}]] — Projeto principal\n"

        # Append if file already exists (multiple sessions same day)
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            # Append new session block
            existing += f"\n\n---\n\n## Sessão Adicional — {time_str}\n\n{summary}\n"
            if decisions:
                existing += "\n### Decisões\n"
                for d in decisions:
                    existing += f"- {d}\n"
            filepath.write_text(existing, encoding="utf-8")
        else:
            filepath.write_text(content, encoding="utf-8")

        return f"Sessão salva: JARVIS/sessions/{filename}"

    # ── Context Retrieval ─────────────────────────────────────

    def get_context(self, project: str) -> str:
        """Get relevant context for a project from memory.

        Returns recent memories, decisions, and session notes related to the project.
        """
        project_lower = project.lower().replace(" ", "-")
        context_parts = []

        # Check for project note
        project_note = self.projects_dir / f"{project}.md"
        if project_note.exists():
            content = project_note.read_text(encoding="utf-8")
            context_parts.append(f"## Nota do Projeto\n{content}")

        # Find recent sessions for this project
        sessions = []
        for f in sorted(self.sessions_dir.glob("*.md"), reverse=True)[:5]:
            try:
                content = f.read_text(encoding="utf-8")
                if project_lower in content.lower():
                    sessions.append(f"- {f.stem}: {self._get_first_heading(content)}")
            except Exception:
                continue

        if sessions:
            context_parts.append("## Sessões Recentes\n" + "\n".join(sessions))

        # Find related decisions
        decisions = []
        for f in sorted(self.decisions_dir.glob("*.md"), reverse=True)[:5]:
            try:
                content = f.read_text(encoding="utf-8")
                if project_lower in content.lower():
                    decisions.append(f"- {f.stem}: {self._get_first_heading(content)}")
            except Exception:
                continue

        if decisions:
            context_parts.append("## Decisões Relacionadas\n" + "\n".join(decisions))

        if not context_parts:
            return f"Nenhum contexto encontrado para o projeto '{project}'. Este é um projeto novo no meu banco de memória."

        return f"# Contexto: {project}\n\n" + "\n\n".join(context_parts)

    # ── Stats & Listing ───────────────────────────────────────

    def count_memories(self) -> int:
        """Count total memory notes."""
        return sum(1 for _ in self.jarvis_dir.rglob("*.md"))

    def list_memories(self, category: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """List recent memories, optionally filtered by category."""
        dir_map = {
            "session": self.sessions_dir,
            "project": self.projects_dir,
            "decision": self.decisions_dir,
        }
        search_dir = dir_map.get(category, self.jarvis_dir)
        glob_pattern = "*.md" if category else "**/*.md"

        files = sorted(search_dir.glob(glob_pattern), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]

        results = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                results.append({
                    "file": str(f.relative_to(self.vault_path)),
                    "name": f.stem,
                    "date": self._extract_date(content) or datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d"),
                    "preview": self._get_first_heading(content) or f.stem,
                })
            except Exception:
                continue

        return results

    def get_status(self) -> Dict:
        """Return status information about the Obsidian connection."""
        return {
            "connected": True,
            "vault_path": str(self.vault_path),
            "memory_count": self.count_memories(),
            "sessions_count": sum(1 for _ in self.sessions_dir.glob("*.md")),
            "projects_count": sum(1 for _ in self.projects_dir.glob("*.md")),
            "decisions_count": sum(1 for _ in self.decisions_dir.glob("*.md")),
        }

    # ── Private Helpers ───────────────────────────────────────

    def _update_project_note(self, project: str, linked_note: str, preview: str):
        """Update or create the project's main note with a new backlink."""
        project_file = self.projects_dir / f"{project}.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if project_file.exists():
            content = project_file.read_text(encoding="utf-8")
            content += f"\n- {timestamp}: [[{linked_note}]] — {preview}\n"
            project_file.write_text(content, encoding="utf-8")
        else:
            content = (
                "---\n"
                f"tags: [jarvis, project, {project.lower().replace(' ', '-')}]\n"
                f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
                "---\n\n"
                f"# {project}\n\n"
                "## Registro de Atividades\n"
                f"- {timestamp}: [[{linked_note}]] — {preview}\n"
            )
            project_file.write_text(content, encoding="utf-8")

    def _extract_date(self, content: str) -> Optional[str]:
        """Extract date from frontmatter."""
        match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", content)
        return match.group(1) if match else None

    def _get_first_heading(self, content: str) -> Optional[str]:
        """Extract the first markdown heading from content."""
        for line in content.split("\n"):
            if line.startswith("# "):
                return line.lstrip("# ").strip()
        return None
