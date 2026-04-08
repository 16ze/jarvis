import os


class ArxivMCP:
    def search(self, query: str, limit: int = 5, sort_by: str = "relevance") -> str:
        try:
            import arxiv
            sort_map = {
                "relevance": arxiv.SortCriterion.Relevance,
                "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
                "submittedDate": arxiv.SortCriterion.SubmittedDate,
            }
            sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)
            search = arxiv.Search(
                query=query,
                max_results=limit,
                sort_by=sort_criterion,
            )
            results = list(search.results())
            if not results:
                return f"Aucun paper trouvé pour '{query}'."
            lines = [f"Papers arXiv pour '{query}':"]
            for r in results:
                arxiv_id = r.entry_id.split("/")[-1]
                title = r.title.replace("\n", " ")
                authors = ", ".join(str(a) for a in r.authors[:3])
                if len(r.authors) > 3:
                    authors += f" et {len(r.authors) - 3} autres"
                published = r.published.strftime("%Y-%m-%d") if r.published else "?"
                lines.append(
                    f"\n  [{arxiv_id}] {title}\n"
                    f"  Auteurs: {authors}\n"
                    f"  Publié: {published}\n"
                    f"  PDF: {r.pdf_url}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur arXiv: {str(e)}"

    def get_paper(self, arxiv_id: str) -> str:
        try:
            import arxiv
            clean_id = arxiv_id.strip().split("/")[-1]
            search = arxiv.Search(id_list=[clean_id])
            results = list(search.results())
            if not results:
                return f"Paper introuvable: {arxiv_id}"
            r = results[0]
            authors = ", ".join(str(a) for a in r.authors)
            published = r.published.strftime("%Y-%m-%d") if r.published else "?"
            updated = r.updated.strftime("%Y-%m-%d") if r.updated else "?"
            categories = ", ".join(r.categories)
            abstract = r.summary.replace("\n", " ")
            return (
                f"Titre: {r.title}\n"
                f"Auteurs: {authors}\n"
                f"Publié: {published} | Mis à jour: {updated}\n"
                f"Catégories: {categories}\n"
                f"PDF: {r.pdf_url}\n"
                f"Page: {r.entry_id}\n\n"
                f"Abstract:\n{abstract}"
            )
        except Exception as e:
            return f"Erreur arXiv: {str(e)}"

    def download_paper(self, arxiv_id: str, output_dir: str = "") -> str:
        try:
            import arxiv
            clean_id = arxiv_id.strip().split("/")[-1]
            search = arxiv.Search(id_list=[clean_id])
            results = list(search.results())
            if not results:
                return f"Paper introuvable: {arxiv_id}"
            r = results[0]
            if not output_dir:
                output_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{clean_id.replace('/', '_')}.pdf"
            output_path = os.path.join(output_dir, filename)
            r.download_pdf(dirpath=output_dir, filename=filename)
            return f"Paper téléchargé: {output_path}"
        except Exception as e:
            return f"Erreur arXiv: {str(e)}"
