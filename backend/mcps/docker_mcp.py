import os

_docker_available = False
try:
    import docker
    _docker_available = True
except ImportError:
    pass


class DockerMCP:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if not _docker_available:
            raise RuntimeError("Librairie 'docker' non installée. Lancez : pip install docker")
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _format_container(self, c) -> str:
        name = c.name
        image = c.image.tags[0] if c.image.tags else c.image.short_id
        status = c.status
        cid = c.short_id
        ports = c.ports
        port_str = ", ".join(
            f"{host[0]['HostPort']}->{container}"
            for container, hosts in ports.items()
            if hosts
            for host in (hosts,)
        ) if ports else "—"
        return f"  {cid} | {name} | {image} | {status} | Ports: {port_str}"

    # ─── CONTAINERS ──────────────────────────────────────────────────────────

    def list_containers(self, all: bool = False) -> str:
        """Liste les containers. Par défaut, uniquement les containers en cours d'exécution."""
        try:
            client = self._get_client()
            containers = client.containers.list(all=all)
            if not containers:
                label = "tous les" if all else "les containers running"
                return f"Aucun container trouvé ({label})."
            lines = [self._format_container(c) for c in containers]
            return f"{len(containers)} container(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Docker list_containers: {str(e)}"

    def get_container_logs(self, container_id_or_name: str, tail: int = 50) -> str:
        """Retourne les dernières lignes de logs d'un container."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id_or_name)
            logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
            if not logs.strip():
                return f"Aucun log disponible pour '{container_id_or_name}'."
            return f"Logs de '{container.name}' (dernières {tail} lignes) :\n{logs}"
        except Exception as e:
            return f"Erreur Docker get_container_logs: {str(e)}"

    def start_container(self, container_id_or_name: str) -> str:
        """Démarre un container arrêté."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id_or_name)
            container.start()
            container.reload()
            return f"Container '{container.name}' démarré. Statut : {container.status}"
        except Exception as e:
            return f"Erreur Docker start_container: {str(e)}"

    def stop_container(self, container_id_or_name: str) -> str:
        """Arrête un container en cours d'exécution."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id_or_name)
            container.stop(timeout=10)
            container.reload()
            return f"Container '{container.name}' arrêté. Statut : {container.status}"
        except Exception as e:
            return f"Erreur Docker stop_container: {str(e)}"

    def restart_container(self, container_id_or_name: str) -> str:
        """Redémarre un container."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id_or_name)
            container.restart(timeout=10)
            container.reload()
            return f"Container '{container.name}' redémarré. Statut : {container.status}"
        except Exception as e:
            return f"Erreur Docker restart_container: {str(e)}"

    # ─── IMAGES ──────────────────────────────────────────────────────────────

    def list_images(self) -> str:
        """Liste les images Docker disponibles localement."""
        try:
            client = self._get_client()
            images = client.images.list()
            if not images:
                return "Aucune image Docker trouvée."
            lines = []
            for img in images:
                tags = ", ".join(img.tags) if img.tags else "<sans tag>"
                size_mb = round(img.attrs.get("Size", 0) / 1_048_576, 1)
                lines.append(f"  {img.short_id} | {tags} | {size_mb} MB")
            return f"{len(images)} image(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Docker list_images: {str(e)}"

    def pull_image(self, image_name: str) -> str:
        """Pull une image depuis Docker Hub ou un registry."""
        try:
            client = self._get_client()
            image = client.images.pull(image_name)
            tags = ", ".join(image.tags) if image.tags else image.short_id
            return f"Image '{image_name}' téléchargée avec succès. Tags : {tags}"
        except Exception as e:
            return f"Erreur Docker pull_image: {str(e)}"

    # ─── STATS ───────────────────────────────────────────────────────────────

    def container_stats(self, container_id_or_name: str) -> str:
        """Snapshot des stats CPU et mémoire d'un container en cours d'exécution."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id_or_name)
            stats = container.stats(stream=False)

            # CPU
            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            num_cpus = stats["cpu_stats"].get("online_cpus") or len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
            cpu_pct = (cpu_delta / system_delta) * num_cpus * 100.0 if system_delta > 0 else 0.0

            # Mémoire
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            mem_cache = stats["memory_stats"].get("stats", {}).get("cache", 0)
            mem_real = mem_usage - mem_cache
            mem_pct = (mem_real / mem_limit) * 100.0 if mem_limit > 0 else 0.0

            mem_mb = round(mem_real / 1_048_576, 1)
            mem_limit_mb = round(mem_limit / 1_048_576, 1)

            # Réseau
            net_io = stats.get("networks", {})
            net_rx = sum(v.get("rx_bytes", 0) for v in net_io.values())
            net_tx = sum(v.get("tx_bytes", 0) for v in net_io.values())

            return (
                f"Stats de '{container.name}' :\n"
                f"  CPU      : {cpu_pct:.2f}%\n"
                f"  Mémoire  : {mem_mb} MB / {mem_limit_mb} MB ({mem_pct:.1f}%)\n"
                f"  Réseau   : RX {round(net_rx/1024, 1)} KB | TX {round(net_tx/1024, 1)} KB"
            )
        except Exception as e:
            return f"Erreur Docker container_stats: {str(e)}"
