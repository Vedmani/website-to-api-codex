#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["httpx", "typer", "rich", "markdownify"]
# ///
"""Retrieve posts from any Substack newsletter via the internal API.

Auth: uses the `substack.sid` httpOnly cookie. Extract it from Chrome
DevTools > Application > Cookies > substack.com, then set SUBSTACK_SID
env var or pass via --sid.
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx
import typer
from markdownify import markdownify as md
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Substack newsletter retrieval CLI")
console = Console()

# ── Auth ──────────────────────────────────────────────────────────────
# The cookie name Substack uses for session auth.  Historically this was
# "connect.sid"; it was renamed to "substack.sid".  If Substack changes
# the name again, update this constant.
COOKIE_NAME = "substack.sid"


def _get_sid(sid_override: str | None = None) -> str:
    sid = sid_override or os.environ.get("SUBSTACK_SID", "")
    if not sid:
        console.print(
            f"[red]Error: No Substack session cookie.[/red]\n"
            f"Set SUBSTACK_SID env var or pass --sid.\n"
            f"To get it: Chrome DevTools > Application > Cookies > substack.com > {COOKIE_NAME}"
        )
        raise typer.Exit(1)
    return sid


def _client(sid: str) -> httpx.Client:
    return httpx.Client(
        cookies={COOKIE_NAME: sid},
        headers={"User-Agent": "SubstackRetrieve/1.0"},
        follow_redirects=True,
        timeout=30.0,
    )


def _fetch_post(client: httpx.Client, base: str, slug: str) -> dict:
    resp = client.get(f"{base}/api/v1/posts/{slug}")
    resp.raise_for_status()
    return resp.json()


# ── Commands ──────────────────────────────────────────────────────────


@app.command()
def list_posts(
    newsletter: str = typer.Argument(
        help="Newsletter base URL (e.g. https://www.lennysnewsletter.com) or subdomain (e.g. lenny)"
    ),
    limit: int = typer.Option(12, help="Number of posts to return (max 50 per page)"),
    offset: int = typer.Option(0, help="Pagination offset"),
    sort: str = typer.Option("new", help="Sort order: 'new' or 'top'"),
    search: str = typer.Option("", help="Full-text search query"),
    output: str = typer.Option("table", help="Output format: 'table' or 'json'"),
    sid: str = typer.Option(None, help="substack.sid cookie value (overrides SUBSTACK_SID env var)"),
):
    """List posts from a Substack newsletter."""
    base = _resolve_base_url(newsletter)
    session = _get_sid(sid)

    all_posts = []
    remaining = limit
    current_offset = offset
    page_size = min(remaining, 50)

    with _client(session) as client:
        while remaining > 0:
            params = {
                "sort": sort,
                "offset": current_offset,
                "limit": page_size,
            }
            if search:
                params["search"] = search

            resp = client.get(f"{base}/api/v1/archive", params=params)
            resp.raise_for_status()
            posts = resp.json()

            if not posts:
                break

            all_posts.extend(posts)
            remaining -= len(posts)
            current_offset += len(posts)
            page_size = min(remaining, 50)

    all_posts = all_posts[:limit]

    if output == "json":
        _print_json(all_posts)
    else:
        _print_table(all_posts)

    console.print(f"\n[dim]{len(all_posts)} posts returned[/dim]")


@app.command()
def get_post(
    newsletter: str = typer.Argument(help="Newsletter base URL or subdomain"),
    slug: str = typer.Argument(help="Post slug (e.g. 'my-post-title')"),
    output: str = typer.Option("summary", help="Output format: 'summary', 'html', or 'json'"),
    sid: str = typer.Option(None, help="substack.sid cookie value"),
):
    """Get a single post by slug (metadata, HTML, or full JSON)."""
    base = _resolve_base_url(newsletter)
    session = _get_sid(sid)

    with _client(session) as client:
        post = _fetch_post(client, base, slug)

    if output == "json":
        console.print_json(json.dumps(post))
    elif output == "html":
        print(post.get("body_html", ""))
    else:
        _print_post_summary(post)


@app.command()
def get_text(
    newsletter: str = typer.Argument(help="Newsletter base URL or subdomain"),
    slug: str = typer.Argument(help="Post slug (e.g. 'my-post-title')"),
    outfile: str = typer.Option(
        None, "--out", "-o",
        help="Output file path. Defaults to /tmp/<slug>.md",
    ),
    sid: str = typer.Option(None, help="substack.sid cookie value"),
):
    """Fetch a post and save it as a Markdown file.

    Converts HTML body to Markdown, adds a metadata header with title,
    subtitle, author, date, and URL. Writes to --out or /tmp/<slug>.md.
    """
    base = _resolve_base_url(newsletter)
    session = _get_sid(sid)

    with _client(session) as client:
        post = _fetch_post(client, base, slug)

    body_html = post.get("body_html", "")
    if not body_html:
        console.print("[red]Error: No body_html in response (post may be paywalled or empty)[/red]")
        raise typer.Exit(1)

    # Convert HTML to Markdown
    body_md = md(body_html, heading_style="ATX", bullets="-", strip=["img"])
    # Clean up excessive blank lines
    body_md = re.sub(r"\n{3,}", "\n\n", body_md)

    # Build metadata header
    title = post.get("title", "Untitled")
    subtitle = post.get("subtitle", "")
    date = (post.get("post_date") or "")[:10]
    url = post.get("canonical_url", "")
    authors = ", ".join(
        b.get("name", "") for b in (post.get("publishedBylines") or [])
    ) or "Unknown"

    header = f"# {title}\n\n"
    if subtitle:
        header += f"*{subtitle}*\n\n"
    header += f"**{authors}** | {date}\n\n"
    header += f"Source: {url}\n\n---\n\n"

    full_md = header + body_md.strip() + "\n"

    # Write to file
    dest = Path(outfile) if outfile else Path(f"/tmp/{slug}.md")
    dest.write_text(full_md, encoding="utf-8")

    console.print(f"[green]Saved to {dest}[/green] ({len(full_md):,} chars, {post.get('wordcount', '?')} words)")
    # Print the path to stdout (useful for piping)
    print(dest)


# ── Helpers ───────────────────────────────────────────────────────────


def _resolve_base_url(newsletter: str) -> str:
    """Accept a full URL or bare subdomain and return the base URL."""
    if newsletter.startswith("http"):
        return newsletter.rstrip("/")
    return f"https://{newsletter}.substack.com"


def _print_table(posts: list[dict]):
    table = Table(show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", width=12)
    table.add_column("Title", min_width=30)
    table.add_column("Audience", width=10)
    table.add_column("Likes", justify="right", width=6)
    table.add_column("Slug", style="dim")

    for i, p in enumerate(posts, 1):
        date = (p.get("post_date") or "")[:10]
        audience = p.get("audience", "")
        audience_style = "green" if audience == "everyone" else "yellow"
        likes = str(p.get("reaction_count") or sum((p.get("reactions") or {}).values()))
        table.add_row(
            str(i),
            date,
            p.get("title", ""),
            f"[{audience_style}]{audience}[/{audience_style}]",
            likes,
            p.get("slug", ""),
        )

    console.print(table)


def _print_json(posts: list[dict]):
    """Print compact JSON with key fields only."""
    compact = [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "slug": p.get("slug"),
            "post_date": p.get("post_date"),
            "audience": p.get("audience"),
            "canonical_url": p.get("canonical_url"),
            "reaction_count": p.get("reaction_count") or sum((p.get("reactions") or {}).values()),
            "comment_count": p.get("comment_count"),
            "wordcount": p.get("wordcount"),
            "subtitle": p.get("subtitle"),
        }
        for p in posts
    ]
    console.print_json(json.dumps(compact))


def _print_post_summary(post: dict):
    body_html = post.get("body_html") or ""
    console.print(f"[bold]{post.get('title', '')}[/bold]")
    console.print(f"[dim]{post.get('subtitle', '')}[/dim]")
    console.print(f"Date: {(post.get('post_date') or '')[:10]}")
    console.print(f"Audience: {post.get('audience', '')}")
    console.print(f"Words: {post.get('wordcount', 'N/A')}")
    console.print(f"HTML length: {len(body_html):,} chars")
    console.print(f"URL: {post.get('canonical_url', '')}")


if __name__ == "__main__":
    app()
