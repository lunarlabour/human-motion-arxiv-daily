import json
import logging
import datetime

import arxiv
import yaml

logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s',
                     datefmt='%m/%d/%Y %H:%M:%S',
                     level=logging.INFO)

ARXIV_ABS_URL = "https://arxiv.org/abs/"


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    # turn each topic's filter list into an arXiv boolean query,
    # restricted to the configured arXiv categories
    default_cats = config.get('categories', [])
    for topic, spec in config['keywords'].items():
        terms = ' OR '.join(f'"{term}"' for term in spec['filters'])
        cats = spec.get('categories', default_cats)
        if cats:
            cat_query = ' OR '.join(f'cat:{c}' for c in cats)
            spec['query'] = f'({terms}) AND ({cat_query})'
        else:
            spec['query'] = terms

    return config


def fetch_papers(query, max_results):
    client = arxiv.Client()
    search = arxiv.Search(query=query,
                           max_results=max_results,
                           sort_by=arxiv.SortCriterion.SubmittedDate)

    papers = {}
    for result in client.results(search):
        paper_id = result.get_short_id().split('v')[0]
        papers[paper_id] = {
            'title': result.title,
            'authors': ", ".join(author.name for author in result.authors),
            'published': str(result.published.date()),
            'updated': str(result.updated.date()),
            'url': ARXIV_ABS_URL + paper_id,
            'abstract': result.summary.replace('\n', ' ').strip(),
        }
        logging.info(f"{paper_id} {result.title}")

    return papers


def update_store(store_path, topic, new_papers):
    try:
        with open(store_path, 'r', encoding='utf-8') as f:
            content = f.read()
            store = json.loads(content) if content else {}
    except FileNotFoundError:
        store = {}

    store.setdefault(topic, {}).update(new_papers)

    with open(store_path, 'w', encoding='utf-8') as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

    return store


def select_recent(store, recent_days):
    cutoff = str(datetime.date.today() - datetime.timedelta(days=recent_days))
    recent = {}
    for topic, papers in store.items():
        kept = {pid: p for pid, p in papers.items() if p['updated'] >= cutoff}
        if kept:
            recent[topic] = kept
    return recent


def render_readme(recent, readme_path, recent_days):
    lines = [
        "# Human Motion Arxiv Daily",
        f"> Updated on {datetime.date.today()}. "
        f"Showing papers from the last {recent_days} days; "
        "full archive in `papers.json`, machine-readable recent data in `recent.json`.",
        "",
    ]

    for topic, papers in recent.items():
        lines.append(f"## {topic}")
        lines.append("")
        lines.append("| Updated | Title | Authors |")
        lines.append("| --- | --- | --- |")

        sorted_papers = sorted(papers.values(),
                                key=lambda p: p['updated'],
                                reverse=True)
        for paper in sorted_papers:
            title = paper['title'].replace('|', '\\|')
            authors = paper['authors'].replace('|', '\\|')
            lines.append(f"| {paper['updated']} | [{title}]({paper['url']}) | {authors} |")
        lines.append("")

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def main():
    config = load_config('config.yaml')
    store_path = config['json_path']
    readme_path = config['readme_path']
    recent_path = config['recent_json_path']
    recent_days = config['recent_days']
    max_results = config['max_results']

    store = {}
    for topic, spec in config['keywords'].items():
        logging.info(f"Searching: {topic}")
        papers = fetch_papers(spec['query'], max_results)
        store = update_store(store_path, topic, papers)

    recent = select_recent(store, recent_days)
    with open(recent_path, 'w', encoding='utf-8') as f:
        json.dump(recent, f, indent=2, ensure_ascii=False)

    render_readme(recent, readme_path, recent_days)


if __name__ == '__main__':
    main()
