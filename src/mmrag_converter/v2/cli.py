import typer
from .processor import V2DocumentProcessor

app = typer.Typer()

@app.command()
def process(input_pdf: str, output_dir: str = "./output"):
    """V2 Document Processing Engine"""
    processor = V2DocumentProcessor(output_dir=output_dir)
    for chunk in processor.process_document(input_pdf):
        print(f"Processed chunk from page {chunk.metadata.page_number}")

if __name__ == "__main__":
    app()