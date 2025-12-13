"""
Update cat breed articles with AI-generated descriptions using Ollama text model.
Generates 4-paragraph descriptions based on breed name.
"""

import subprocess
import tempfile
import os
import requests

# SSH connection details
SSH_HOST = "65.181.112.77"
SSH_USER = "root"
SSH_PASSWORD = "T917nY9ILYmJGtUq"
PLINK_PATH = r"C:\Program Files\PuTTY\plink.exe"
PSCP_PATH = r"C:\Program Files\PuTTY\pscp.exe"
SSH_HOSTKEY = "ssh-ed25519 255 SHA256:EnWadrWQBKWVjQ8UV9ynQuSJbAjEuaMimajwlXoZecw"

# Use a fast text model
MODEL = "huihui_ai/dolphin3-abliterated:8b"


def run_ssh_command(command: str, timeout: int = 120) -> str:
    """Execute command on remote Drupal server via SSH."""
    ssh_cmd = [
        PLINK_PATH, "-ssh", "-pw", SSH_PASSWORD,
        "-hostkey", SSH_HOSTKEY,
        f"{SSH_USER}@{SSH_HOST}", command
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout


def generate_description(breed_name: str) -> str:
    """Generate a 4-paragraph description for a cat breed using Ollama."""

    prompt = f"""Write exactly 4 paragraphs about the {breed_name} cat breed for a pet information website.

Paragraph 1: Describe the physical appearance - coat color and texture, eye color, body size and shape, and distinctive features that make this breed recognizable.

Paragraph 2: Explain the personality and temperament. Are they playful, calm, affectionate, or independent? How do they interact with families, children, and other pets?

Paragraph 3: Cover care requirements including grooming needs, exercise requirements, dietary considerations, and common health issues to watch for.

Paragraph 4: Summarize what potential owners should expect. Who is this breed best suited for? What living situation works best?

Write in a warm, informative tone. Each paragraph should be 3-4 sentences. Do not use any markdown, headers, or bullet points - just plain paragraphs separated by blank lines."""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 800}
            },
            timeout=120
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
    except Exception as e:
        print(f"    Error: {e}")
    return ""


def get_cat_articles() -> list:
    """Get all cat article node IDs and titles."""
    query = '''cd /var/www/drupal && vendor/bin/drush sqlq "SELECT nid, title FROM node_field_data WHERE type='cats' ORDER BY title" --extra=-N'''
    output = run_ssh_command(query)
    articles = []
    for line in output.strip().split('\n'):
        if line.strip():
            parts = line.split('\t')
            if len(parts) >= 2:
                articles.append({'nid': parts[0], 'title': parts[1]})
    return articles


def update_article_body(nid: str, html_body: str) -> bool:
    """Update the body of a cat article."""
    # Write body to temp file
    body_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    body_file.write(html_body)
    body_file.close()

    # Upload body file
    upload_cmd = [
        PSCP_PATH, "-pw", SSH_PASSWORD, "-hostkey", SSH_HOSTKEY,
        body_file.name, f"{SSH_USER}@{SSH_HOST}:/tmp/body_{nid}.txt"
    ]
    subprocess.run(upload_cmd, capture_output=True)

    # Update the node
    command = f'''cd /var/www/drupal && vendor/bin/drush php:eval '
$node = \\Drupal\\node\\Entity\\Node::load({nid});
if ($node) {{
    $body = file_get_contents("/tmp/body_{nid}.txt");
    $node->set("body", ["value" => $body, "format" => "full_html"]);
    $node->save();
    echo "OK";
}}' '''
    result = run_ssh_command(command, timeout=60)

    # Cleanup
    os.unlink(body_file.name)
    run_ssh_command(f"rm -f /tmp/body_{nid}.txt")

    return "OK" in result


def main():
    print("=" * 60)
    print("Updating Cat Breed Articles with AI Descriptions")
    print(f"Using model: {MODEL}")
    print("=" * 60)

    articles = get_cat_articles()
    print(f"\nFound {len(articles)} articles to process.\n")

    processed = 0
    errors = 0

    for article in articles:
        nid = article['nid']
        title = article['title']

        print(f"[{nid}] {title}... ", end="", flush=True)

        description = generate_description(title)
        if not description:
            print("FAILED (no response)")
            errors += 1
            continue

        # Split into paragraphs and format as HTML
        paragraphs = [p.strip() for p in description.split('\n\n') if p.strip()]
        if len(paragraphs) < 2:
            paragraphs = [p.strip() for p in description.split('\n') if p.strip()]

        html_body = '\n'.join([f'<p>{p}</p>' for p in paragraphs if p])

        if update_article_body(nid, html_body):
            print("OK")
            processed += 1
        else:
            print("FAILED (update)")
            errors += 1

    print("\n" + "=" * 60)
    print(f"Done! Updated: {processed}, Errors: {errors}")
    print("=" * 60)

    # Clear cache
    print("\nClearing Drupal cache...")
    run_ssh_command("cd /var/www/drupal && vendor/bin/drush cr")
    print("Complete!")


if __name__ == "__main__":
    main()
