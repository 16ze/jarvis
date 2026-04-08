# ─────────────────────────────────────────────────────────────────────────────
# MCP TOOL DECLARATIONS — Gemini function_declarations format
# Un préfixe par service pour éviter les collisions de noms
# ─────────────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════════
# COMMUNICATION
# ═══════════════════════════════════════════════════════════════════════════════

# ── SLACK ────────────────────────────────────────────────────────────────────
slack_list_channels_tool = {
    "name": "slack_list_channels",
    "description": "Liste tous les channels Slack disponibles (ID + nom).",
    "parameters": {"type": "OBJECT", "properties": {}}
}
slack_read_channel_tool = {
    "name": "slack_read_channel",
    "description": "Lit les derniers messages d'un channel Slack.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "channel_id": {"type": "STRING", "description": "ID du channel Slack (ex: C012AB3CD)"},
            "limit": {"type": "INTEGER", "description": "Nombre de messages à récupérer (défaut 20)"}
        },
        "required": ["channel_id"]
    }
}
slack_send_message_tool = {
    "name": "slack_send_message",
    "description": "Envoie un message dans un channel ou DM Slack.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "channel_id": {"type": "STRING", "description": "ID du channel ou utilisateur"},
            "text": {"type": "STRING", "description": "Texte du message"}
        },
        "required": ["channel_id", "text"]
    }
}
slack_search_messages_tool = {
    "name": "slack_search_messages",
    "description": "Recherche des messages dans Slack par mots-clés.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Mots-clés à chercher"},
            "count": {"type": "INTEGER", "description": "Nombre de résultats (défaut 10)"}
        },
        "required": ["query"]
    }
}

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
telegram_send_message_tool = {
    "name": "telegram_send_message",
    "description": "Envoie un message Telegram à Bryan (ou à un chat_id spécifique).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "Texte du message"},
            "chat_id": {"type": "STRING", "description": "ID du destinataire (optionnel, utilise le défaut)"}
        },
        "required": ["text"]
    }
}
telegram_send_photo_tool = {
    "name": "telegram_send_photo",
    "description": "Envoie une image via Telegram.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "photo_url": {"type": "STRING", "description": "URL publique de l'image"},
            "caption": {"type": "STRING", "description": "Légende optionnelle"},
            "chat_id": {"type": "STRING", "description": "ID destinataire (optionnel)"}
        },
        "required": ["photo_url"]
    }
}
telegram_get_updates_tool = {
    "name": "telegram_get_updates",
    "description": "Récupère les derniers messages reçus sur le bot Telegram.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de messages (défaut 10)"}
        }
    }
}

# ── WHATSAPP ──────────────────────────────────────────────────────────────────
whatsapp_send_message_tool = {
    "name": "whatsapp_send_message",
    "description": "Envoie un message WhatsApp. Format numéro: '33612345678@s.whatsapp.net' (indicatif pays sans +).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "number": {"type": "STRING", "description": "Numéro WhatsApp (ex: 33612345678@s.whatsapp.net)"},
            "text": {"type": "STRING", "description": "Texte du message"}
        },
        "required": ["number", "text"]
    }
}
whatsapp_send_media_tool = {
    "name": "whatsapp_send_media",
    "description": "Envoie un fichier ou une image via WhatsApp.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "number": {"type": "STRING", "description": "Numéro WhatsApp"},
            "media_url": {"type": "STRING", "description": "URL publique du fichier"},
            "caption": {"type": "STRING", "description": "Légende optionnelle"}
        },
        "required": ["number", "media_url"]
    }
}
whatsapp_get_messages_tool = {
    "name": "whatsapp_get_messages",
    "description": "Récupère les messages récents d'une conversation WhatsApp.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "number": {"type": "STRING", "description": "Numéro WhatsApp"},
            "limit": {"type": "INTEGER", "description": "Nombre de messages (défaut 20)"}
        },
        "required": ["number"]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTIVITÉ
# ═══════════════════════════════════════════════════════════════════════════════

# ── NOTION ────────────────────────────────────────────────────────────────────
notion_search_tool = {
    "name": "notion_search",
    "description": "Recherche des pages et bases de données dans Notion.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Terme de recherche"},
            "limit": {"type": "INTEGER", "description": "Nombre de résultats (défaut 10)"}
        },
        "required": ["query"]
    }
}
notion_get_page_tool = {
    "name": "notion_get_page",
    "description": "Lit le contenu d'une page Notion par son ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "page_id": {"type": "STRING", "description": "ID de la page Notion"}
        },
        "required": ["page_id"]
    }
}
notion_create_page_tool = {
    "name": "notion_create_page",
    "description": "Crée une nouvelle page dans Notion.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "parent_id": {"type": "STRING", "description": "ID de la page ou base de données parente"},
            "title": {"type": "STRING", "description": "Titre de la nouvelle page"},
            "content": {"type": "STRING", "description": "Contenu texte initial (optionnel)"}
        },
        "required": ["parent_id", "title"]
    }
}
notion_query_database_tool = {
    "name": "notion_query_database",
    "description": "Requête une base de données Notion avec des filtres optionnels.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "database_id": {"type": "STRING", "description": "ID de la base de données Notion"},
            "filter_json": {"type": "STRING", "description": "Filtres JSON optionnels (format Notion API)"}
        },
        "required": ["database_id"]
    }
}
notion_append_page_tool = {
    "name": "notion_append_page",
    "description": "Ajoute du contenu à la fin d'une page Notion existante.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "page_id": {"type": "STRING", "description": "ID de la page"},
            "content": {"type": "STRING", "description": "Texte à ajouter"}
        },
        "required": ["page_id", "content"]
    }
}

# ── GOOGLE DRIVE / SHEETS / DOCS ─────────────────────────────────────────────
drive_list_files_tool = {
    "name": "drive_list_files",
    "description": "Liste les fichiers Google Drive.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Recherche par nom (ex: 'name contains devis')"},
            "limit": {"type": "INTEGER", "description": "Nombre de fichiers (défaut 10)"}
        }
    }
}
drive_read_file_tool = {
    "name": "drive_read_file",
    "description": "Lit le contenu d'un fichier Google Drive (texte, Google Doc, etc.).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_id": {"type": "STRING", "description": "ID du fichier Google Drive"}
        },
        "required": ["file_id"]
    }
}
drive_upload_file_tool = {
    "name": "drive_upload_file",
    "description": "Upload un fichier local vers Google Drive.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "local_path": {"type": "STRING", "description": "Chemin local du fichier"},
            "folder_id": {"type": "STRING", "description": "ID du dossier destination (optionnel)"}
        },
        "required": ["local_path"]
    }
}
sheets_read_tool = {
    "name": "sheets_read",
    "description": "Lit une plage de cellules dans un Google Sheet.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "spreadsheet_id": {"type": "STRING", "description": "ID du Google Sheet"},
            "range": {"type": "STRING", "description": "Plage de cellules (ex: Sheet1!A1:Z100)"}
        },
        "required": ["spreadsheet_id"]
    }
}
sheets_write_tool = {
    "name": "sheets_write",
    "description": "Écrit des valeurs dans un Google Sheet (remplace les cellules).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "spreadsheet_id": {"type": "STRING", "description": "ID du Google Sheet"},
            "range": {"type": "STRING", "description": "Plage cible (ex: Sheet1!A1)"},
            "values_json": {"type": "STRING", "description": "Tableau 2D JSON (ex: [[\"val1\", \"val2\"]])"}
        },
        "required": ["spreadsheet_id", "range", "values_json"]
    }
}
sheets_append_tool = {
    "name": "sheets_append",
    "description": "Ajoute des lignes à la fin d'un Google Sheet.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "spreadsheet_id": {"type": "STRING", "description": "ID du Google Sheet"},
            "range": {"type": "STRING", "description": "Plage de base (ex: Sheet1!A:A)"},
            "values_json": {"type": "STRING", "description": "Tableau 2D JSON des lignes à ajouter"}
        },
        "required": ["spreadsheet_id", "range", "values_json"]
    }
}
docs_read_tool = {
    "name": "docs_read",
    "description": "Lit le contenu texte d'un Google Doc.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "doc_id": {"type": "STRING", "description": "ID du Google Doc"}
        },
        "required": ["doc_id"]
    }
}

# ── LINEAR ────────────────────────────────────────────────────────────────────
linear_list_issues_tool = {
    "name": "linear_list_issues",
    "description": "Liste les issues Linear avec filtres optionnels.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "team_id": {"type": "STRING", "description": "ID de l'équipe (optionnel)"},
            "status": {"type": "STRING", "description": "Statut: Todo / In Progress / Done / Cancelled"},
            "limit": {"type": "INTEGER", "description": "Nombre d'issues (défaut 20)"}
        }
    }
}
linear_get_issue_tool = {
    "name": "linear_get_issue",
    "description": "Récupère le détail d'une issue Linear par son ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "issue_id": {"type": "STRING", "description": "ID de l'issue Linear"}
        },
        "required": ["issue_id"]
    }
}
linear_create_issue_tool = {
    "name": "linear_create_issue",
    "description": "Crée une nouvelle issue dans Linear.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Titre de l'issue"},
            "description": {"type": "STRING", "description": "Description détaillée"},
            "team_id": {"type": "STRING", "description": "ID de l'équipe"},
            "priority": {"type": "INTEGER", "description": "Priorité: 0=no, 1=urgent, 2=high, 3=medium, 4=low"}
        },
        "required": ["title"]
    }
}
linear_update_issue_tool = {
    "name": "linear_update_issue",
    "description": "Met à jour une issue Linear (statut, titre, description).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "issue_id": {"type": "STRING", "description": "ID de l'issue"},
            "status": {"type": "STRING", "description": "Nouveau statut"},
            "title": {"type": "STRING", "description": "Nouveau titre"},
            "description": {"type": "STRING", "description": "Nouvelle description"}
        },
        "required": ["issue_id"]
    }
}
linear_list_projects_tool = {
    "name": "linear_list_projects",
    "description": "Liste les projets Linear.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "team_id": {"type": "STRING", "description": "Filtrer par équipe (optionnel)"}
        }
    }
}
linear_list_teams_tool = {
    "name": "linear_list_teams",
    "description": "Liste les équipes Linear disponibles.",
    "parameters": {"type": "OBJECT", "properties": {}}
}

# ── STRIPE ────────────────────────────────────────────────────────────────────
stripe_list_customers_tool = {
    "name": "stripe_list_customers",
    "description": "Liste les clients Stripe.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de clients (défaut 10)"},
            "email": {"type": "STRING", "description": "Filtrer par email (optionnel)"}
        }
    }
}
stripe_get_customer_tool = {
    "name": "stripe_get_customer",
    "description": "Récupère les détails d'un client Stripe.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "customer_id": {"type": "STRING", "description": "ID Stripe du client (cus_...)"}
        },
        "required": ["customer_id"]
    }
}
stripe_list_payments_tool = {
    "name": "stripe_list_payments",
    "description": "Liste les paiements Stripe récents.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de paiements (défaut 10)"},
            "customer_id": {"type": "STRING", "description": "Filtrer par client (optionnel)"}
        }
    }
}
stripe_list_invoices_tool = {
    "name": "stripe_list_invoices",
    "description": "Liste les factures Stripe.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de factures (défaut 10)"},
            "customer_id": {"type": "STRING", "description": "Filtrer par client (optionnel)"}
        }
    }
}
stripe_get_balance_tool = {
    "name": "stripe_get_balance",
    "description": "Récupère le solde disponible du compte Stripe.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
stripe_create_invoice_item_tool = {
    "name": "stripe_create_invoice_item",
    "description": "Crée un item de facturation Stripe pour un client.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "customer_id": {"type": "STRING", "description": "ID du client Stripe"},
            "amount_cents": {"type": "INTEGER", "description": "Montant en centimes (ex: 150000 = 1500€)"},
            "currency": {"type": "STRING", "description": "Devise (ex: eur, usd)"},
            "description": {"type": "STRING", "description": "Description de la prestation"}
        },
        "required": ["customer_id", "amount_cents", "currency", "description"]
    }
}
stripe_send_invoice_tool = {
    "name": "stripe_send_invoice",
    "description": "Finalise et envoie une facture Stripe par email.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "invoice_id": {"type": "STRING", "description": "ID de la facture Stripe (in_...)"}
        },
        "required": ["invoice_id"]
    }
}

# ── QONTO ─────────────────────────────────────────────────────────────────────
qonto_get_balance_tool = {
    "name": "qonto_get_balance",
    "description": "Récupère le solde du compte bancaire Qonto.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
qonto_list_transactions_tool = {
    "name": "qonto_list_transactions",
    "description": "Liste les transactions bancaires Qonto.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de transactions (défaut 25)"},
            "status": {"type": "STRING", "description": "Statut: completed / pending / declined"}
        }
    }
}
qonto_get_organization_tool = {
    "name": "qonto_get_organization",
    "description": "Récupère les informations de l'organisation Qonto.",
    "parameters": {"type": "OBJECT", "properties": {}}
}

# ═══════════════════════════════════════════════════════════════════════════════
# DEV & INFRA
# ═══════════════════════════════════════════════════════════════════════════════

# ── SUPABASE ──────────────────────────────────────────────────────────────────
supabase_query_tool = {
    "name": "supabase_query",
    "description": "Exécute un SELECT sur une table Supabase avec filtres optionnels.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "table": {"type": "STRING", "description": "Nom de la table"},
            "filters_json": {"type": "STRING", "description": "Filtres JSON: [{\"column\":\"id\",\"op\":\"eq\",\"value\":\"123\"}]"},
            "limit": {"type": "INTEGER", "description": "Nombre de lignes (défaut 20)"},
            "columns": {"type": "STRING", "description": "Colonnes à sélectionner (défaut *)"}
        },
        "required": ["table"]
    }
}
supabase_insert_tool = {
    "name": "supabase_insert",
    "description": "Insère une ligne dans une table Supabase.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "table": {"type": "STRING", "description": "Nom de la table"},
            "data_json": {"type": "STRING", "description": "Données JSON à insérer (objet)"}
        },
        "required": ["table", "data_json"]
    }
}
supabase_update_tool = {
    "name": "supabase_update",
    "description": "Met à jour des lignes dans une table Supabase.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "table": {"type": "STRING", "description": "Nom de la table"},
            "filters_json": {"type": "STRING", "description": "Conditions WHERE en JSON"},
            "data_json": {"type": "STRING", "description": "Champs à mettre à jour en JSON"}
        },
        "required": ["table", "filters_json", "data_json"]
    }
}
supabase_delete_tool = {
    "name": "supabase_delete",
    "description": "Supprime des lignes d'une table Supabase.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "table": {"type": "STRING", "description": "Nom de la table"},
            "filters_json": {"type": "STRING", "description": "Conditions WHERE en JSON"}
        },
        "required": ["table", "filters_json"]
    }
}
supabase_sql_tool = {
    "name": "supabase_sql",
    "description": "Exécute une requête SQL brute sur Supabase.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Requête SQL à exécuter"}
        },
        "required": ["query"]
    }
}
supabase_list_tables_tool = {
    "name": "supabase_list_tables",
    "description": "Liste toutes les tables de la base de données Supabase.",
    "parameters": {"type": "OBJECT", "properties": {}}
}

# ── VERCEL ────────────────────────────────────────────────────────────────────
vercel_list_projects_tool = {
    "name": "vercel_list_projects",
    "description": "Liste les projets Vercel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de projets (défaut 20)"}
        }
    }
}
vercel_get_project_tool = {
    "name": "vercel_get_project",
    "description": "Récupère les détails d'un projet Vercel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "ID ou nom du projet"}
        },
        "required": ["project_id"]
    }
}
vercel_list_deployments_tool = {
    "name": "vercel_list_deployments",
    "description": "Liste les derniers deployments Vercel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "Filtrer par projet (optionnel)"},
            "limit": {"type": "INTEGER", "description": "Nombre de deployments (défaut 10)"}
        }
    }
}
vercel_get_deployment_tool = {
    "name": "vercel_get_deployment",
    "description": "Récupère le statut et les infos d'un deployment Vercel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "deployment_id": {"type": "STRING", "description": "ID du deployment"}
        },
        "required": ["deployment_id"]
    }
}
vercel_get_logs_tool = {
    "name": "vercel_get_logs",
    "description": "Récupère les logs de build d'un deployment Vercel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "deployment_id": {"type": "STRING", "description": "ID du deployment"}
        },
        "required": ["deployment_id"]
    }
}

# ── GITHUB ────────────────────────────────────────────────────────────────────
github_list_repos_tool = {
    "name": "github_list_repos",
    "description": "Liste les repos GitHub de l'utilisateur.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de repos (défaut 20)"}
        }
    }
}
github_get_repo_tool = {
    "name": "github_get_repo",
    "description": "Récupère les informations d'un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo": {"type": "STRING", "description": "Format owner/repo (optionnel, utilise le repo par défaut)"}
        }
    }
}
github_list_issues_tool = {
    "name": "github_list_issues",
    "description": "Liste les issues d'un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo": {"type": "STRING", "description": "Format owner/repo"},
            "state": {"type": "STRING", "description": "open / closed / all (défaut open)"},
            "limit": {"type": "INTEGER", "description": "Nombre d'issues (défaut 10)"}
        }
    }
}
github_create_issue_tool = {
    "name": "github_create_issue",
    "description": "Crée une issue dans un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Titre de l'issue"},
            "body": {"type": "STRING", "description": "Description détaillée"},
            "repo": {"type": "STRING", "description": "Format owner/repo"}
        },
        "required": ["title"]
    }
}
github_list_prs_tool = {
    "name": "github_list_prs",
    "description": "Liste les pull requests d'un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo": {"type": "STRING", "description": "Format owner/repo"},
            "state": {"type": "STRING", "description": "open / closed / all"},
            "limit": {"type": "INTEGER", "description": "Nombre de PRs (défaut 10)"}
        }
    }
}
github_list_commits_tool = {
    "name": "github_list_commits",
    "description": "Liste les derniers commits d'un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo": {"type": "STRING", "description": "Format owner/repo"},
            "branch": {"type": "STRING", "description": "Branche (défaut main)"},
            "limit": {"type": "INTEGER", "description": "Nombre de commits (défaut 10)"}
        }
    }
}
github_search_code_tool = {
    "name": "github_search_code",
    "description": "Recherche du code dans un repo GitHub.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Termes de recherche"},
            "repo": {"type": "STRING", "description": "Limiter à un repo owner/repo (optionnel)"}
        },
        "required": ["query"]
    }
}

# ── DOCKER ────────────────────────────────────────────────────────────────────
docker_list_containers_tool = {
    "name": "docker_list_containers",
    "description": "Liste les containers Docker (running par défaut).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "all": {"type": "BOOLEAN", "description": "True pour inclure les containers stoppés"}
        }
    }
}
docker_get_logs_tool = {
    "name": "docker_get_logs",
    "description": "Récupère les logs d'un container Docker.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "container": {"type": "STRING", "description": "ID ou nom du container"},
            "tail": {"type": "INTEGER", "description": "Nombre de lignes (défaut 50)"}
        },
        "required": ["container"]
    }
}
docker_start_tool = {
    "name": "docker_start",
    "description": "Démarre un container Docker.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "container": {"type": "STRING", "description": "ID ou nom du container"}
        },
        "required": ["container"]
    }
}
docker_stop_tool = {
    "name": "docker_stop",
    "description": "Arrête un container Docker.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "container": {"type": "STRING", "description": "ID ou nom du container"}
        },
        "required": ["container"]
    }
}
docker_restart_tool = {
    "name": "docker_restart",
    "description": "Redémarre un container Docker.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "container": {"type": "STRING", "description": "ID ou nom du container"}
        },
        "required": ["container"]
    }
}
docker_list_images_tool = {
    "name": "docker_list_images",
    "description": "Liste les images Docker disponibles localement.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
docker_stats_tool = {
    "name": "docker_stats",
    "description": "Récupère les stats CPU/mémoire d'un container Docker.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "container": {"type": "STRING", "description": "ID ou nom du container"}
        },
        "required": ["container"]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SMART HOME & PERSO
# ═══════════════════════════════════════════════════════════════════════════════

# ── HOME ASSISTANT ────────────────────────────────────────────────────────────
ha_get_states_tool = {
    "name": "ha_get_states",
    "description": "Liste les entités Home Assistant (lights, switches, sensors, etc.).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "domain": {"type": "STRING", "description": "Filtrer par domain: light, switch, sensor, climate, media_player... (optionnel)"}
        }
    }
}
ha_get_entity_tool = {
    "name": "ha_get_entity",
    "description": "Récupère l'état et les attributs d'une entité Home Assistant.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "entity_id": {"type": "STRING", "description": "ID de l'entité (ex: light.salon, sensor.temperature)"}
        },
        "required": ["entity_id"]
    }
}
ha_call_service_tool = {
    "name": "ha_call_service",
    "description": "Appelle un service Home Assistant (contrôle d'entité générique).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "domain": {"type": "STRING", "description": "Domaine du service (ex: light, switch, climate)"},
            "service": {"type": "STRING", "description": "Nom du service (ex: turn_on, set_temperature)"},
            "entity_id": {"type": "STRING", "description": "Entité cible (optionnel)"},
            "data_json": {"type": "STRING", "description": "Paramètres additionnels en JSON (optionnel)"}
        },
        "required": ["domain", "service"]
    }
}
# ── Domotique locale Tuya ─────────────────────────────────────────────────────
list_smart_devices_tool = {
    "name": "list_smart_devices",
    "description": "Liste les appareils Tuya connectés sur le réseau local (ampoules, prises). Utilise cet outil pour voir quels appareils sont disponibles, leur état (allumé/éteint) et leur alias.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
control_light_tool = {
    "name": "control_light",
    "description": "Contrôle une ampoule ou un appareil Tuya local par son alias (ex: 'CHAMBRE PRINCIPAL'). Utilise TOUJOURS cet outil pour allumer, éteindre, changer la couleur ou la luminosité d'une lumière. Ne jamais utiliser ha_turn_on pour les lumières Tuya.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {"type": "STRING", "description": "Alias de l'appareil (ex: 'CHAMBRE PRINCIPAL')"},
            "action": {"type": "STRING", "description": "Action à effectuer : 'turn_on', 'turn_off', ou 'set'"},
            "brightness": {"type": "NUMBER", "description": "Luminosité entre 0 et 100 (optionnel)"},
            "color": {"type": "STRING", "description": "Couleur en anglais : red, green, blue, yellow, orange, purple, pink, white, warm, cool (optionnel)"}
        },
        "required": ["target", "action"]
    }
}

refresh_tuya_devices_tool = {
    "name": "refresh_tuya_devices",
    "description": "Resynchronise les alias des appareils Tuya depuis le cloud SmartLife/Tuya. À utiliser quand les noms dans SmartLife ont changé et ne correspondent plus à ce qu'Ada connaît.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}

# ── CHROMECAST ───────────────────────────────────────────────────────────────
get_chromecast_status_tool = {
    "name": "get_chromecast_status",
    "description": "Récupère l'état actuel du Chromecast : ce qui joue en ce moment, l'app active, le volume. Utilise cet outil quand Monsieur demande ce qui passe sur la TV ou sur le Chromecast.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
control_chromecast_tool = {
    "name": "control_chromecast",
    "description": "Contrôle la lecture sur le Chromecast : play, pause, stop ou réglage du volume.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action : 'play' (reprendre), 'pause' (mettre en pause), 'stop' (arrêter)."
            },
            "volume": {
                "type": "NUMBER",
                "description": "Volume optionnel entre 0.0 et 1.0 (ex: 0.5 pour 50%). Si fourni, règle le volume sans changer l'état de lecture."
            }
        },
        "required": ["action"]
    }
}
play_youtube_on_chromecast_tool = {
    "name": "play_youtube_on_chromecast",
    "description": "Lance une vidéo YouTube sur le Chromecast. Utilise cet outil quand Monsieur demande de mettre une vidéo YouTube sur la TV.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "video_url": {
                "type": "STRING",
                "description": "URL complète de la vidéo YouTube (ex: https://www.youtube.com/watch?v=dQw4w9WgXcQ)."
            }
        },
        "required": ["video_url"]
    }
}
play_media_on_chromecast_tool = {
    "name": "play_media_on_chromecast",
    "description": "Lance un média quelconque (vidéo, audio, image) sur le Chromecast via son URL directe.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {
                "type": "STRING",
                "description": "URL directe du fichier média à lancer."
            },
            "media_type": {
                "type": "STRING",
                "description": "Type MIME du média (ex: 'video/mp4', 'audio/mp3', 'image/jpeg'). Défaut: 'video/mp4'."
            }
        },
        "required": ["url"]
    }
}

ha_turn_on_tool = {
    "name": "ha_turn_on",
    "description": "Allume une entité Home Assistant (lumière, prise, etc.).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "entity_id": {"type": "STRING", "description": "ID de l'entité (ex: light.chambre)"}
        },
        "required": ["entity_id"]
    }
}
ha_turn_off_tool = {
    "name": "ha_turn_off",
    "description": "Éteint une entité Home Assistant.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "entity_id": {"type": "STRING", "description": "ID de l'entité"}
        },
        "required": ["entity_id"]
    }
}

# ── SPOTIFY ───────────────────────────────────────────────────────────────────
spotify_current_tool = {
    "name": "spotify_current",
    "description": "Récupère la lecture Spotify en cours (titre, artiste, progression).",
    "parameters": {"type": "OBJECT", "properties": {}}
}
spotify_play_tool = {
    "name": "spotify_play",
    "description": "Lance la lecture Spotify (optionnel: URI d'une track, album ou playlist).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "uri": {"type": "STRING", "description": "URI Spotify (ex: spotify:track:...) — vide pour reprendre"},
            "device_id": {"type": "STRING", "description": "ID de l'appareil (optionnel)"}
        }
    }
}
spotify_pause_tool = {
    "name": "spotify_pause",
    "description": "Met en pause la lecture Spotify.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
spotify_next_tool = {
    "name": "spotify_next",
    "description": "Passe à la piste suivante sur Spotify.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
spotify_previous_tool = {
    "name": "spotify_previous",
    "description": "Revient à la piste précédente sur Spotify.",
    "parameters": {"type": "OBJECT", "properties": {}}
}
spotify_volume_tool = {
    "name": "spotify_volume",
    "description": "Règle le volume Spotify (0 à 100).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "volume_percent": {"type": "INTEGER", "description": "Volume de 0 à 100"}
        },
        "required": ["volume_percent"]
    }
}
spotify_search_tool = {
    "name": "spotify_search",
    "description": "Recherche des tracks, albums ou playlists sur Spotify.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Terme de recherche"},
            "search_type": {"type": "STRING", "description": "track / album / playlist / artist (défaut track)"},
            "limit": {"type": "INTEGER", "description": "Nombre de résultats (défaut 5)"}
        },
        "required": ["query"]
    }
}
spotify_playlists_tool = {
    "name": "spotify_playlists",
    "description": "Liste les playlists de l'utilisateur Spotify.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de playlists (défaut 20)"}
        }
    }
}

# ── APPLE HEALTH ──────────────────────────────────────────────────────────────
health_steps_tool = {
    "name": "health_steps",
    "description": "Récupère les données de pas quotidiens depuis l'export Apple Health.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {"type": "INTEGER", "description": "Nombre de jours à analyser (défaut 7)"}
        }
    }
}
health_sleep_tool = {
    "name": "health_sleep",
    "description": "Récupère les données de sommeil depuis l'export Apple Health.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {"type": "INTEGER", "description": "Nombre de nuits à analyser (défaut 7)"}
        }
    }
}
health_heart_rate_tool = {
    "name": "health_heart_rate",
    "description": "Récupère les données de fréquence cardiaque depuis l'export Apple Health.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {"type": "INTEGER", "description": "Nombre de jours (défaut 3)"}
        }
    }
}
health_activity_tool = {
    "name": "health_activity",
    "description": "Récupère le résumé d'activité (calories, minutes d'exercice) depuis Apple Health.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {"type": "INTEGER", "description": "Nombre de jours (défaut 7)"}
        }
    }
}

# ── GOOGLE MAPS ───────────────────────────────────────────────────────────────
maps_directions_tool = {
    "name": "maps_directions",
    "description": "Calcule l'itinéraire entre deux points via Google Maps.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "origin": {"type": "STRING", "description": "Adresse ou coordonnées de départ"},
            "destination": {"type": "STRING", "description": "Adresse ou coordonnées d'arrivée"},
            "mode": {"type": "STRING", "description": "driving / walking / transit / bicycling (défaut driving)"}
        },
        "required": ["origin", "destination"]
    }
}
maps_travel_time_tool = {
    "name": "maps_travel_time",
    "description": "Calcule uniquement la durée de trajet entre deux points.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "origin": {"type": "STRING", "description": "Point de départ"},
            "destination": {"type": "STRING", "description": "Destination"},
            "mode": {"type": "STRING", "description": "driving / walking / transit (défaut driving)"}
        },
        "required": ["origin", "destination"]
    }
}
maps_search_places_tool = {
    "name": "maps_search_places",
    "description": "Recherche des lieux à proximité via Google Maps.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Terme de recherche (ex: restaurant japonais Paris 11)"},
            "location": {"type": "STRING", "description": "Centre de recherche (adresse ou lat,lng)"},
            "radius": {"type": "INTEGER", "description": "Rayon en mètres (défaut 5000)"}
        },
        "required": ["query"]
    }
}
maps_geocode_tool = {
    "name": "maps_geocode",
    "description": "Convertit une adresse en coordonnées GPS.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "address": {"type": "STRING", "description": "Adresse à géocoder"}
        },
        "required": ["address"]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# RECHERCHE & INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

# ── YOUTUBE ───────────────────────────────────────────────────────────────────
youtube_search_tool = {
    "name": "youtube_search",
    "description": "Recherche des vidéos YouTube.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Terme de recherche"},
            "limit": {"type": "INTEGER", "description": "Nombre de résultats (défaut 5)"}
        },
        "required": ["query"]
    }
}
youtube_video_info_tool = {
    "name": "youtube_video_info",
    "description": "Récupère les informations d'une vidéo YouTube (titre, description, durée, stats).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "video": {"type": "STRING", "description": "ID vidéo YouTube ou URL complète"}
        },
        "required": ["video"]
    }
}
youtube_transcript_tool = {
    "name": "youtube_transcript",
    "description": "Récupère la transcription/sous-titres d'une vidéo YouTube.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "video": {"type": "STRING", "description": "ID vidéo YouTube ou URL complète"}
        },
        "required": ["video"]
    }
}

# ── WIKIPEDIA ─────────────────────────────────────────────────────────────────
wikipedia_search_tool = {
    "name": "wikipedia_search",
    "description": "Recherche des articles Wikipedia.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Terme de recherche"},
            "limit": {"type": "INTEGER", "description": "Nombre de résultats (défaut 5)"}
        },
        "required": ["query"]
    }
}
wikipedia_article_tool = {
    "name": "wikipedia_article",
    "description": "Lit le contenu d'un article Wikipedia.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Titre exact de l'article"},
            "lang": {"type": "STRING", "description": "Langue: fr / en / de / es... (défaut fr)"}
        },
        "required": ["title"]
    }
}

# ── ARXIV ─────────────────────────────────────────────────────────────────────
arxiv_search_tool = {
    "name": "arxiv_search",
    "description": "Recherche des papers scientifiques sur ArXiv (IA, tech, physique, etc.).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Termes de recherche"},
            "limit": {"type": "INTEGER", "description": "Nombre de résultats (défaut 5)"},
            "sort_by": {"type": "STRING", "description": "relevance / lastUpdatedDate / submittedDate"}
        },
        "required": ["query"]
    }
}
arxiv_paper_tool = {
    "name": "arxiv_paper",
    "description": "Récupère les détails complets d'un paper ArXiv.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "arxiv_id": {"type": "STRING", "description": "ID ArXiv (ex: 2303.08774)"}
        },
        "required": ["arxiv_id"]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# FINANCE & ADMIN
# ═══════════════════════════════════════════════════════════════════════════════

# (Qonto déjà déclaré ci-dessus dans Productivité)
# Budget perso via Google Sheets — utilise sheets_read/sheets_append avec BUDGET_SHEET_ID

# ═══════════════════════════════════════════════════════════════════════════════
# CRÉATION & MÉDIAS
# ═══════════════════════════════════════════════════════════════════════════════

# ── CANVA ─────────────────────────────────────────────────────────────────────
canva_list_designs_tool = {
    "name": "canva_list_designs",
    "description": "Liste les designs Canva de l'utilisateur.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Nombre de designs (défaut 20)"}
        }
    }
}
canva_get_design_tool = {
    "name": "canva_get_design",
    "description": "Récupère les informations d'un design Canva.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "design_id": {"type": "STRING", "description": "ID du design Canva"}
        },
        "required": ["design_id"]
    }
}
canva_export_design_tool = {
    "name": "canva_export_design",
    "description": "Exporte un design Canva en image ou PDF.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "design_id": {"type": "STRING", "description": "ID du design Canva"},
            "format": {"type": "STRING", "description": "Format: png / jpg / pdf / gif / svg / pptx (défaut png)"}
        },
        "required": ["design_id"]
    }
}

# ── FIGMA ─────────────────────────────────────────────────────────────────────
figma_list_files_tool = {
    "name": "figma_list_files",
    "description": "Liste les fichiers Figma d'une équipe ou d'un projet.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "team_id": {"type": "STRING", "description": "ID de l'équipe Figma"},
            "project_id": {"type": "STRING", "description": "ID du projet Figma (optionnel)"}
        }
    }
}
figma_get_file_tool = {
    "name": "figma_get_file",
    "description": "Récupère la structure d'un fichier Figma (pages, frames, composants).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_key": {"type": "STRING", "description": "Clé du fichier Figma (dans l'URL)"}
        },
        "required": ["file_key"]
    }
}
figma_export_node_tool = {
    "name": "figma_export_node",
    "description": "Exporte un élément Figma en image.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_key": {"type": "STRING", "description": "Clé du fichier Figma"},
            "node_id": {"type": "STRING", "description": "ID du nœud à exporter"},
            "format": {"type": "STRING", "description": "Format: png / jpg / svg / pdf (défaut png)"}
        },
        "required": ["file_key", "node_id"]
    }
}

# ── ELEVENLABS ────────────────────────────────────────────────────────────────
elevenlabs_tts_tool = {
    "name": "elevenlabs_tts",
    "description": "Génère un fichier audio à partir de texte via ElevenLabs.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "Texte à synthétiser"},
            "voice_id": {"type": "STRING", "description": "ID de la voix (optionnel, utilise la voix par défaut)"},
            "output_path": {"type": "STRING", "description": "Chemin de sauvegarde .mp3 (optionnel)"}
        },
        "required": ["text"]
    }
}
elevenlabs_list_voices_tool = {
    "name": "elevenlabs_list_voices",
    "description": "Liste les voix disponibles sur ElevenLabs.",
    "parameters": {"type": "OBJECT", "properties": {}}
}

# ── REPLICATE ─────────────────────────────────────────────────────────────────
replicate_generate_image_tool = {
    "name": "replicate_generate_image",
    "description": "Génère une image via Replicate (SDXL ou autre modèle).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Description de l'image à générer"},
            "model": {"type": "STRING", "description": "Modèle Replicate (défaut: stability-ai/sdxl)"},
            "width": {"type": "INTEGER", "description": "Largeur en pixels (défaut 1024)"},
            "height": {"type": "INTEGER", "description": "Hauteur en pixels (défaut 1024)"}
        },
        "required": ["prompt"]
    }
}
replicate_run_model_tool = {
    "name": "replicate_run_model",
    "description": "Exécute n'importe quel modèle Replicate avec des paramètres personnalisés.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "model_version": {"type": "STRING", "description": "Version du modèle (ex: owner/model:version_hash)"},
            "input_json": {"type": "STRING", "description": "Paramètres d'entrée en JSON"}
        },
        "required": ["model_version", "input_json"]
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-CORRECTION (Jarvis repo)
# ═══════════════════════════════════════════════════════════════════════════════

jarvis_read_file_tool = {
    "name": "jarvis_read_file",
    "description": "Lit un fichier du repo jarvis (/Users/bryandev/jarvis/). Utilise pour inspecter ton propre code.",
    "parameters": {"type": "OBJECT", "properties": {
        "path": {"type": "STRING", "description": "Chemin absolu ou relatif au repo jarvis. Ex: 'backend/ada.py' ou '/Users/bryandev/jarvis/backend/ada.py'"}
    }, "required": ["path"]}
}

jarvis_write_file_tool = {
    "name": "jarvis_write_file",
    "description": "Écrit un fichier dans le repo jarvis. Valide la syntaxe Python et crée un backup git automatique. N'utilise QUE pour corriger ton propre code.",
    "parameters": {"type": "OBJECT", "properties": {
        "path": {"type": "STRING", "description": "Chemin du fichier à écrire (doit être dans /Users/bryandev/jarvis/)"},
        "content": {"type": "STRING", "description": "Contenu complet du fichier"}
    }, "required": ["path", "content"]}
}

jarvis_list_files_tool = {
    "name": "jarvis_list_files",
    "description": "Liste les fichiers d'un dossier du repo jarvis.",
    "parameters": {"type": "OBJECT", "properties": {
        "path": {"type": "STRING", "description": "Dossier à lister. Laisser vide pour la racine du repo."}
    }}
}

jarvis_git_commit_tool = {
    "name": "jarvis_git_commit",
    "description": "Crée un commit git dans le repo jarvis après une modification.",
    "parameters": {"type": "OBJECT", "properties": {
        "message": {"type": "STRING", "description": "Message de commit (convention: 'fix: ...' ou 'feat: ...')"}
    }, "required": ["message"]}
}

self_correct_file_tool = {
    "name": "self_correct_file",
    "description": "Utilise Claude Opus 4.6 pour analyser une erreur dans un fichier et appliquer automatiquement la correction. Crée un commit après. Utilise quand tu détectes une erreur dans ton propre code.",
    "parameters": {"type": "OBJECT", "properties": {
        "file_path": {"type": "STRING", "description": "Chemin absolu du fichier à corriger"},
        "error_description": {"type": "STRING", "description": "Description précise de l'erreur : traceback complet + comportement attendu vs observé"}
    }, "required": ["file_path", "error_description"]}
}

# ═══════════════════════════════════════════════════════════════════════════════
# RAPPELS
# ═══════════════════════════════════════════════════════════════════════════════

ada_sleep_tool = {
    "name": "ada_sleep",
    "description": (
        "Met Ada en mode veille. À appeler quand Monsieur dit 'mets-toi en pause', "
        "'dors', 'silence', 'mode veille' ou toute formulation équivalente. "
        "En mode veille Ada écoute mais ne répond à rien sauf à son prénom."
    ),
    "parameters": {"type": "OBJECT", "properties": {}}
}

ada_wake_tool = {
    "name": "ada_wake",
    "description": (
        "Sort Ada du mode veille. À appeler OBLIGATOIREMENT dès qu'Ada entend son prénom "
        "après avoir été mise en veille, avant de répondre quoi que ce soit."
    ),
    "parameters": {"type": "OBJECT", "properties": {}}
}

reminder_set_tool = {
    "name": "reminder_set",
    "description": (
        "Crée un rappel qui se déclenchera à une date/heure précise. "
        "Ada parlera ou enverra un message Telegram au moment du rappel. "
        "Utilise cet outil dès que Monsieur demande de lui rappeler quelque chose."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {"type": "STRING", "description": "Le contenu du rappel, tel qu'Ada devra le lire."},
            "datetime_iso": {"type": "STRING", "description": "Date et heure ISO 8601, ex: '2026-04-03T15:30:00'. Heure locale Paris."},
        },
        "required": ["message", "datetime_iso"]
    }
}

reminder_list_tool = {
    "name": "reminder_list",
    "description": "Liste tous les rappels actifs (non encore déclenchés).",
    "parameters": {"type": "OBJECT", "properties": {}}
}

reminder_delete_tool = {
    "name": "reminder_delete",
    "description": "Supprime un rappel par son ID (obtenu via reminder_list).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "reminder_id": {"type": "STRING", "description": "ID du rappel à supprimer (ex: 'a3f2b1c0')."},
        },
        "required": ["reminder_id"]
    }
}

# ── SELF-EVOLUTION ────────────────────────────────────────────────────────────
self_evolve_tool = {
    "name": "self_evolve",
    "description": (
        "Crée automatiquement un nouveau connecteur MCP quand Ada n'a pas l'outil "
        "pour accomplir une mission. Appelle cet outil UNIQUEMENT après avoir constaté "
        "qu'aucun outil existant ne peut réaliser la tâche demandée. "
        "Ada se redémarre automatiquement après la création pour activer le nouvel outil."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {
                "type": "STRING",
                "description": "Ce que tu voulais accomplir (ex: 'envoyer un SMS via Twilio')"
            },
            "failed_context": {
                "type": "STRING",
                "description": "Ce qui a échoué et pourquoi (outil manquant, erreur reçue, contexte)"
            }
        },
        "required": ["goal", "failed_context"]
    }
}

# ── ADVANCED BROWSER ──────────────────────────────────────────────────────────
advanced_web_navigation_tool = {
    "name": "advanced_web_navigation",
    "description": (
        "Navigue sur le web de manière complexe (clics, formulaires, "
        "navigation multi-pages, connexion aux comptes) pour accomplir "
        "des missions métier ou personnelles. Utilise les sessions "
        "existantes (LinkedIn, Gmail, etc.) si disponibles."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mission": {
                "type": "STRING",
                "description": "Description complète de la mission web à accomplir en langage naturel."
            }
        },
        "required": ["mission"]
    },
    "behavior": "NON_BLOCKING"
}

# ── OS CONTROL (Full Computer Use) ───────────────────────────────────────────
execute_pc_task_tool = {
    "name": "execute_pc_task",
    "description": (
        "Prend le contrôle total du Mac (souris, clavier, applications) "
        "pour accomplir n'importe quelle tâche complexe de manière autonome. "
        "Prend des screenshots en continu, analyse l'écran et agit jusqu'à completion. "
        "Peut ouvrir le Finder, déplacer des fichiers, coder dans VS Code, changer les réglages système, etc."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task_description": {
                "type": "STRING",
                "description": "Description complète de la tâche à accomplir sur le Mac."
            }
        },
        "required": ["task_description"]
    },
    "behavior": "NON_BLOCKING"
}

# ── CAMÉRA TUYA PTZ ──────────────────────────────────────────────────────────
camera_switch_tool = {
    "name": "camera_switch",
    "description": (
        "Bascule la source vidéo d'Ada. Utilise 'tuya_camera' pour activer la caméra SmartLife PTZ connectée au salon/entrée, "
        "'webcam' pour la caméra de l'ordinateur, 'screen' pour le partage d'écran, 'none' pour désactiver. "
        "Appelle cet outil quand on te demande de regarder par la caméra, voir ce qui se passe dans la pièce, ou surveiller."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "source": {
                "type": "STRING",
                "description": "Source vidéo : 'tuya_camera' | 'webcam' | 'screen' | 'none'",
            }
        },
        "required": ["source"],
    },
}

camera_ptz_move_tool = {
    "name": "camera_ptz_move",
    "description": (
        "Fait pivoter la caméra PTZ SmartLife dans une direction. "
        "Directions acceptées : up/haut, down/bas, left/gauche, right/droite, "
        "upper_right/haut-droite, lower_right/bas-droite, lower_left/bas-gauche, upper_left/haut-gauche. "
        "duration_ms : durée du mouvement en millisecondes (100–5000, défaut 600)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "direction": {
                "type": "STRING",
                "description": "Direction : up, down, left, right, upper_right, lower_right, lower_left, upper_left (ou équivalent français)",
            },
            "duration_ms": {
                "type": "NUMBER",
                "description": "Durée du mouvement en ms (défaut 600, max 5000)",
            },
        },
        "required": ["direction"],
    },
}

camera_goto_preset_tool = {
    "name": "camera_goto_preset",
    "description": (
        "Positionne la caméra PTZ sur une position préenregistrée (preset). "
        "Les presets sont des positions mémorisées dans la caméra via l'app SmartLife (preset 1, 2, 3…)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "preset": {
                "type": "NUMBER",
                "description": "Numéro du preset (1, 2, 3…)",
            }
        },
        "required": ["preset"],
    },
}

camera_tracking_tool = {
    "name": "camera_tracking",
    "description": (
        "Active ou désactive le suivi automatique de mouvement (auto-tracking PTZ) de la caméra SmartLife. "
        "Quand activé, la caméra pivote automatiquement pour suivre toute personne ou objet en mouvement dans le champ de vision. "
        "Utilise cet outil quand Bryan dit 'suis les mouvements', 'active le tracking', 'arrête de suivre'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "enabled": {
                "type": "BOOLEAN",
                "description": "True pour activer le suivi, False pour désactiver",
            }
        },
        "required": ["enabled"],
    },
}

camera_motion_detect_tool = {
    "name": "camera_motion_detect",
    "description": (
        "Active ou désactive la détection de mouvement de la caméra SmartLife, et règle la sensibilité. "
        "Quand activée avec surveillance (camera_watch), Ada prévient Bryan via Telegram dès qu'un mouvement est détecté."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "enabled": {
                "type": "BOOLEAN",
                "description": "True pour activer la détection, False pour désactiver",
            },
            "sensitivity": {
                "type": "STRING",
                "description": "Sensibilité : 'low'/'faible', 'medium'/'moyenne' (défaut), 'high'/'élevée'",
            },
        },
        "required": ["enabled"],
    },
}

camera_watch_tool = {
    "name": "camera_watch",
    "description": (
        "Démarre ou arrête la surveillance active de mouvement via la caméra SmartLife. "
        "Quand active, Ada poll les événements et envoie une alerte Telegram avec photo dès qu'un mouvement est détecté. "
        "Utilise cet outil quand Bryan dit 'surveille', 'préviens-moi si quelqu'un bouge', 'arrête de surveiller'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "enabled": {
                "type": "BOOLEAN",
                "description": "True pour démarrer la surveillance, False pour l'arrêter",
            },
            "with_snapshot": {
                "type": "BOOLEAN",
                "description": "True pour envoyer une photo avec chaque alerte (défaut True)",
            },
        },
        "required": ["enabled"],
    },
}

camera_look_tool = {
    "name": "camera_look",
    "description": (
        "Capture une photo depuis la caméra SmartLife PTZ et décrit ce qu'Ada voit. "
        "Utilise cet outil en mode texte/Telegram pour répondre à 'qu'est-ce que tu vois ?', "
        "'y a-t-il quelqu'un ?', 'regarde si…', etc. "
        "En mode voix, la caméra est déjà active en continu — cet outil force une capture instantanée avec analyse."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {
                "type": "STRING",
                "description": "Question spécifique à analyser sur l'image (ex: 'y a-t-il quelqu'un ?', 'que fait la personne ?')",
            }
        },
        "required": [],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# LISTE CONSOLIDÉE — à importer dans ada.py
# ─────────────────────────────────────────────────────────────────────────────

# ── TWILIO (auto-généré) ─────────────────────────────────────────────
# ── TWILIO ────────────────────────────────────────────────────────────────────
twilio_send_sms_tool = {
    "name": "twilio_send_sms",
    "description": "Envoie un message SMS à un numéro de téléphone spécifié. Le numéro de l'expéditeur est configuré par défaut.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "to": {"type": "STRING", "description": "Le numéro de téléphone du destinataire au format international (ex: +33612345678)."},
            "body": {"type": "STRING", "description": "Le contenu du message SMS à envoyer."}
        },
        "required": ["to", "body"]
    }
}

MCP_TOOLS = [
    # Communication
    slack_list_channels_tool, slack_read_channel_tool, slack_send_message_tool, slack_search_messages_tool,
    telegram_send_message_tool, telegram_send_photo_tool, telegram_get_updates_tool,
    whatsapp_send_message_tool, whatsapp_send_media_tool, whatsapp_get_messages_tool,
    # Productivité
    notion_search_tool, notion_get_page_tool, notion_create_page_tool, notion_query_database_tool, notion_append_page_tool,
    drive_list_files_tool, drive_read_file_tool, drive_upload_file_tool,
    sheets_read_tool, sheets_write_tool, sheets_append_tool, docs_read_tool,
    linear_list_issues_tool, linear_get_issue_tool, linear_create_issue_tool, linear_update_issue_tool, linear_list_projects_tool, linear_list_teams_tool,
    stripe_list_customers_tool, stripe_get_customer_tool, stripe_list_payments_tool, stripe_list_invoices_tool,
    stripe_get_balance_tool, stripe_create_invoice_item_tool, stripe_send_invoice_tool,
    qonto_get_balance_tool, qonto_list_transactions_tool, qonto_get_organization_tool,
    # Dev & Infra
    supabase_query_tool, supabase_insert_tool, supabase_update_tool, supabase_delete_tool, supabase_sql_tool, supabase_list_tables_tool,
    vercel_list_projects_tool, vercel_get_project_tool, vercel_list_deployments_tool, vercel_get_deployment_tool, vercel_get_logs_tool,
    github_list_repos_tool, github_get_repo_tool, github_list_issues_tool, github_create_issue_tool,
    github_list_prs_tool, github_list_commits_tool, github_search_code_tool,
    docker_list_containers_tool, docker_get_logs_tool, docker_start_tool, docker_stop_tool,
    docker_restart_tool, docker_list_images_tool, docker_stats_tool,
    # Smart Home — Tuya local (priorité sur Home Assistant)
    list_smart_devices_tool, control_light_tool, refresh_tuya_devices_tool,
    ha_get_states_tool, ha_get_entity_tool, ha_call_service_tool, ha_turn_on_tool, ha_turn_off_tool,
    # Chromecast
    get_chromecast_status_tool, control_chromecast_tool, play_youtube_on_chromecast_tool, play_media_on_chromecast_tool,
    spotify_current_tool, spotify_play_tool, spotify_pause_tool, spotify_next_tool, spotify_previous_tool,
    spotify_volume_tool, spotify_search_tool, spotify_playlists_tool,
    health_steps_tool, health_sleep_tool, health_heart_rate_tool, health_activity_tool,
    maps_directions_tool, maps_travel_time_tool, maps_search_places_tool, maps_geocode_tool,
    # Recherche
    youtube_search_tool, youtube_video_info_tool, youtube_transcript_tool,
    wikipedia_search_tool, wikipedia_article_tool,
    arxiv_search_tool, arxiv_paper_tool,
    advanced_web_navigation_tool,
    # OS Control
    execute_pc_task_tool,
    # Création
    canva_list_designs_tool, canva_get_design_tool, canva_export_design_tool,
    figma_list_files_tool, figma_get_file_tool, figma_export_node_tool,
    elevenlabs_tts_tool, elevenlabs_list_voices_tool,
    replicate_generate_image_tool, replicate_run_model_tool,
    # Self-correction (Jarvis repo)
    jarvis_read_file_tool, jarvis_write_file_tool, jarvis_list_files_tool, jarvis_git_commit_tool, self_correct_file_tool,
    # Rappels
    reminder_set_tool, reminder_list_tool, reminder_delete_tool,
    # Mode veille
    ada_sleep_tool, ada_wake_tool,
    # Self-evolution
    self_evolve_tool,
    # Caméra Tuya PTZ
    camera_switch_tool, camera_ptz_move_tool, camera_goto_preset_tool, camera_look_tool,
    camera_tracking_tool, camera_motion_detect_tool, camera_watch_tool,
    # Twilio
    twilio_send_sms_tool,
    # Multi-user recognition
    {
        "name": "remember_for_user",
        "description": (
            "Enregistre une préférence, une habitude ou un fait pour l'utilisateur actuellement identifié. "
            "Utilise ce tool dès qu'un utilisateur mentionne une préférence, une habitude ou une information "
            "personnelle (ex: 'j'aime le café', 'je travaille le matin', 'j'ai deux enfants'). "
            "Ne l'utilise pas pour Bryan si ce n'est pas Bryan qui parle."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {
                    "type": "STRING",
                    "description": "ID de l'utilisateur : 'bryan', 'rose', ou le prénom en minuscules d'un invité."
                },
                "memory_type": {
                    "type": "STRING",
                    "description": "Type de mémoire : 'preference', 'habit', ou 'fact'."
                },
                "content": {
                    "type": "STRING",
                    "description": "La préférence, habitude ou fait à enregistrer."
                }
            },
            "required": ["user_id", "memory_type", "content"]
        }
    },
    {
        "name": "enroll_voice",
        "description": (
            "Lance l'enrollment vocal pour un utilisateur. À utiliser quand Bryan demande à Ada "
            "d'enregistrer la voix de quelqu'un (ex: 'Ada, enregistre la voix de Rose'). "
            "L'enrollment dure 25 secondes — prévenir l'utilisateur de parler normalement."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {
                    "type": "STRING",
                    "description": "ID de l'utilisateur à enregistrer : 'bryan', 'rose', ou prénom invité."
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "who_is_speaking",
        "description": (
            "Retourne la liste des utilisateurs actuellement identifiés (voix + visage). "
            "Utilise ce tool quand Ada n'est pas sûre de qui lui parle ou quand Bryan demande "
            "'qui est là ?' / 'tu reconnais qui ?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
]

MCP_TOOL_NAMES = {t["name"] for t in MCP_TOOLS}
