"""
Update cat breed articles with AI-generated descriptions using moondream vision model.
Analyzes each cat image and generates a 4-paragraph description about the breed.
"""

import base64
import os
import subprocess
import tempfile

# SSH connection details
SSH_HOST = "65.181.112.77"
SSH_USER = "root"
SSH_PASSWORD = "T917nY9ILYmJGtUq"
PLINK_PATH = r"C:\Program Files\PuTTY\plink.exe"
PSCP_PATH = r"C:\Program Files\PuTTY\pscp.exe"
SSH_HOSTKEY = "ssh-ed25519 255 SHA256:EnWadrWQBKWVjQ8UV9ynQuSJbAjEuaMimajwlXoZecw"


def run_ssh_command(command: str, timeout: int = 120) -> str:
    """Execute command on remote Drupal server via SSH."""
    ssh_cmd = [
        PLINK_PATH,
        "-ssh",
        "-pw",
        SSH_PASSWORD,
        "-hostkey",
        SSH_HOSTKEY,
        f"{SSH_USER}@{SSH_HOST}",
        command,
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout


def download_file(remote_path: str, local_path: str) -> bool:
    """Download a file from the Drupal server."""
    cmd = [
        PSCP_PATH,
        "-pw",
        SSH_PASSWORD,
        "-hostkey",
        SSH_HOSTKEY,
        f"{SSH_USER}@{SSH_HOST}:{remote_path}",
        local_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_description_with_vision(image_path: str, breed_name: str) -> str:
    """Use moondream vision model to analyze the cat image and generate a description."""

    # Read image and encode to base64
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""Write a 4-paragraph article about the {breed_name} cat breed:

Paragraph 1: Physical appearance - coat, eyes, body, unique features.
Paragraph 2: Personality and temperament with families.
Paragraph 3: Care requirements - grooming, exercise, health.
Paragraph 4: What owners should expect.

Write plain text paragraphs only, no markdown."""

    # Create the request payload
    payload = {
        "model": "moondream",
        "prompt": prompt,
        "images": [image_data],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1500},
    }

    # Call Ollama API
    import requests

    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=180)
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "")
    except Exception as e:
        print(f"Error calling moondream: {e}")

    return ""


def get_cat_articles() -> list:
    """Get all cat articles with their image paths."""
    # Query to get node data with image file paths
    query = """
    cd /var/www/drupal && vendor/bin/drush sqlq "
        SELECT
            n.nid,
            n.title,
            fm.uri as image_uri
        FROM node_field_data n
        JOIN node__field_cat_image ci ON n.nid = ci.entity_id
        JOIN file_managed fm ON ci.field_cat_image_target_id = fm.fid
        WHERE n.type = 'cats'
        ORDER BY n.title
    " --extra=-N
    """

    output = run_ssh_command(query)
    articles = []

    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            nid, title, image_uri = parts[0], parts[1], parts[2]
            # Convert public:// URI to actual path
            image_path = image_uri.replace("public://", "/var/www/drupal/web/sites/default/files/")
            articles.append({"nid": nid, "title": title, "image_path": image_path})

    return articles


def update_article_body(nid: str, new_body: str) -> bool:
    """Update the body of a cat article."""
    # Escape special characters for SQL
    escaped_body = new_body.replace("'", "''").replace("\\", "\\\\")

    # Create PHP script to update the node
    php_script = f"""
$node = \\Drupal\\node\\Entity\\Node::load({nid});
if ($node) {{
    $node->set("body", [
        "value" => '{escaped_body}',
        "format" => "full_html"
    ]);
    $node->save();
    echo "Updated node {nid}";
}}
"""

    # Write to temp file and execute
    temp_php = f"/tmp/update_node_{nid}.php"

    # Use a simpler approach - write the body to a file and use drush
    command = f"""cd /var/www/drupal && vendor/bin/drush php:eval '
$node = \\Drupal\\node\\Entity\\Node::load({nid});
if ($node) {{
    $body = file_get_contents("/tmp/body_{nid}.txt");
    $node->set("body", ["value" => $body, "format" => "full_html"]);
    $node->save();
    echo "Updated";
}}
' """

    # First, upload the body content
    body_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    body_file.write(new_body)
    body_file.close()

    # Upload body file
    upload_cmd = [
        PSCP_PATH,
        "-pw",
        SSH_PASSWORD,
        "-hostkey",
        SSH_HOSTKEY,
        body_file.name,
        f"{SSH_USER}@{SSH_HOST}:/tmp/body_{nid}.txt",
    ]
    subprocess.run(upload_cmd, capture_output=True)

    # Run the update
    result = run_ssh_command(command, timeout=60)

    # Cleanup
    os.unlink(body_file.name)
    run_ssh_command(f"rm -f /tmp/body_{nid}.txt")

    return "Updated" in result


def main():
    print("=" * 60)
    print("Updating Cat Breed Articles with AI-Generated Descriptions")
    print("=" * 60)

    # Get all cat articles
    print("\nFetching cat articles...")
    articles = get_cat_articles()
    print(f"Found {len(articles)} articles to process.\n")

    # Create temp directory for images
    temp_dir = tempfile.mkdtemp(prefix="cat_images_")

    processed = 0
    errors = 0

    for article in articles:
        nid = article["nid"]
        title = article["title"]
        remote_image = article["image_path"]

        print(f"\n[{nid}] {title}")
        print("    Downloading image...")

        # Download the image
        local_image = os.path.join(temp_dir, f"cat_{nid}.jpg")
        if not download_file(remote_image, local_image):
            print("    ERROR: Failed to download image")
            errors += 1
            continue

        print("    Generating description with moondream...")
        description = generate_description_with_vision(local_image, title)

        if not description:
            print("    ERROR: Failed to generate description")
            errors += 1
            continue

        # Clean up the description
        description = description.strip()

        # Format as HTML paragraphs
        paragraphs = [p.strip() for p in description.split("\n\n") if p.strip()]
        if len(paragraphs) < 4:
            # Try splitting by single newlines if double didn't work
            paragraphs = [p.strip() for p in description.split("\n") if p.strip()]

        html_body = "\n".join([f"<p>{p}</p>" for p in paragraphs[:4]])

        print("    Updating article...")
        if update_article_body(nid, html_body):
            print("    SUCCESS: Article updated")
            processed += 1
        else:
            print("    ERROR: Failed to update article")
            errors += 1

        # Clean up temp image
        os.unlink(local_image)

    # Cleanup temp directory
    os.rmdir(temp_dir)

    print("\n" + "=" * 60)
    print(f"Completed! Processed: {processed}, Errors: {errors}")
    print("=" * 60)

    # Clear Drupal cache
    print("\nClearing Drupal cache...")
    run_ssh_command("cd /var/www/drupal && vendor/bin/drush cr")
    print("Done!")


if __name__ == "__main__":
    main()
