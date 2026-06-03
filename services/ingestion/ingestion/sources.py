from dataclasses import dataclass


@dataclass(frozen=True)
class WebSource:
    name: str
    seed_urls: tuple[str, ...]
    allow_prefix: tuple[str, ...]  # only crawl URLs starting with these
    deny_substr: tuple[str, ...] = ()


SOURCES: dict[str, WebSource] = {
    "kubernetes": WebSource(
        name="kubernetes",
        seed_urls=(
            "https://kubernetes.io/docs/concepts/overview/",
            "https://kubernetes.io/docs/concepts/workloads/",
            "https://kubernetes.io/docs/concepts/services-networking/",
        ),
        allow_prefix=("https://kubernetes.io/docs/concepts/",),
        deny_substr=("?", "#"),
    ),
    "spring": WebSource(
        name="spring",
        seed_urls=(
            "https://docs.spring.io/spring-boot/reference/index.html",
            "https://docs.spring.io/spring-boot/reference/using/index.html",
        ),
        allow_prefix=("https://docs.spring.io/spring-boot/reference/",),
        deny_substr=("?", "#"),
    ),
    "angular": WebSource(
        name="angular",
        seed_urls=(
            "https://angular.dev/overview",
            "https://angular.dev/essentials",
        ),
        allow_prefix=("https://angular.dev/",),
        deny_substr=("?", "#", "/api/", "/cli/"),
    ),
}
