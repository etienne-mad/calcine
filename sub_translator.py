import re
import requests
import argparse
import os
import time
from typing import List, Dict
from datetime import datetime

class SubtitleTranslator:
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1/messages"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "x-api-key": self.api_key,  # Change back to x-api-key
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
    def parse_srt(self, content: str) -> List[Dict[str, str]]:
        """Parse SRT content into a list of subtitle dictionaries."""
        subtitle_pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.*?\n)*?)(?:\n|$)'
        matches = re.finditer(subtitle_pattern, content, re.MULTILINE)
        
        subtitles = []
        for match in matches:
            subtitle = {
                'index': match.group(1),
                'start_time': match.group(2),
                'end_time': match.group(3),
                'text': match.group(4).strip()
            }
            subtitles.append(subtitle)
        return subtitles

    def translate_text(self, text: str, target_language: str = "French") -> str:
        """Translate text using Claude API with retry mechanism."""
        # prompt = f"Translate the following text to {target_language}, keeping the same format and style:\n\n{text}"
        # prompt = f"Translate the following text to {target_language}, keeping the same format and style except use lowercase whenever you should. DO NOT ADD ANY INTRODUCTORY TEST LIKE voici la traduction or whatever...:\n\n{text}"
        prompt = f"Translate only the following text to {target_language}. Use lowercase unless grammatically required. Do not add any commentary or additional text:\n\n{text}"
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "model": "claude-3-opus-20240229",
            "max_tokens": 1024
        }
        # print("Request headers:", self.headers)  # Debug line
        # print("Request data:", data)  # Debug line

        for attempt in range(self.max_retries):
            try:
                response = requests.post(self.base_url, headers=self.headers, json=data)
                response.raise_for_status()
                return response.json()['content'][0]['text']
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"Translation attempt {attempt + 1} failed: {e}")
                    if hasattr(e, 'response'):
                        print(f"Response content: {e.response.content}")
                    print(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    print(f"Final translation attempt failed: {e}")
                    if hasattr(e, 'response'):
                        print(f"Response content: {e.response.content}")
                    return text

    def save_progress(self, translated_subtitles: List[Dict[str, str]], output_file: str):
        """Save current progress to output file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            for subtitle in translated_subtitles:
                f.write(f"{subtitle['index']}\n")
                f.write(f"{subtitle['start_time']} --> {subtitle['end_time']}\n")
                f.write(f"{subtitle['text']}\n\n")

    def create_backup(self, file_path: str) -> str:
        """Create a backup of the file with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.{timestamp}.backup"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as src:
                with open(backup_path, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
        return backup_path

    def translate_subtitles(self, input_file: str, output_file: str, target_language: str = "French"):
        """Translate entire subtitle file and save to output file with progress saving."""
        print(f"Translating {input_file} to {output_file}...")
        
        # Create backup of existing output file if it exists
        if os.path.exists(output_file):
            backup_file = self.create_backup(output_file)
            print(f"Created backup of existing output file: {backup_file}")
        
        # Read input file
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse subtitles
        subtitles = self.parse_srt(content)
        total_subtitles = len(subtitles)
        print(f"Found {total_subtitles} subtitles to translate")

        # Translate in smaller batches to optimize API calls
        batch_size = 5
        translated_subtitles = []
        
        # Create progress file
        progress_file = f"{output_file}.progress"
        
        try:
            for i in range(0, total_subtitles, batch_size):
                batch = subtitles[i:i + batch_size]
                current_batch = i//batch_size + 1
                total_batches = (total_subtitles + batch_size - 1)//batch_size
                print(f"\nTranslating batch {current_batch}/{total_batches} (subtitles {i+1}-{min(i+batch_size, total_subtitles)})")
                
                # Add a small delay between batches to avoid rate limiting
                if i > 0:
                    time.sleep(1)
                
                # Combine texts for batch translation
                combined_text = "\n---\n".join(sub['text'] for sub in batch)
                translated_text = self.translate_text(combined_text, target_language)
                
                # Split translated text back into individual subtitles
                translated_parts = translated_text.split("\n---\n")
                
                for j, part in enumerate(translated_parts):
                    subtitle = batch[j].copy()
                    subtitle['text'] = part.strip()
                    translated_subtitles.append(subtitle)
                
                # Save progress after each batch
                self.save_progress(translated_subtitles, progress_file)
                
                # Print progress
                progress = (i + len(batch)) / total_subtitles * 100
                print(f"Progress: {progress:.1f}%")
        
        except KeyboardInterrupt:
            print("\nTranslation interrupted by user. Saving progress...")
            self.save_progress(translated_subtitles, progress_file)
            print(f"Progress saved to {progress_file}")
            return
        except Exception as e:
            print(f"\nUnexpected error occurred: {e}")
            self.save_progress(translated_subtitles, progress_file)
            print(f"Progress saved to {progress_file}")
            raise
        
        # Write final output and clean up progress file
        self.save_progress(translated_subtitles, output_file)
        if os.path.exists(progress_file):
            os.remove(progress_file)
        
        print(f"\nTranslation completed! Output saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Translate subtitle files using Claude API')
    parser.add_argument('input', help='Input subtitle file path')
    parser.add_argument('output', help='Output subtitle file path')
    parser.add_argument('--language', '-l', default='French', help='Target language (default: French)')
    parser.add_argument('--api-key', default=os.environ.get('CLAUDE_API_KEY'), 
                      help='Claude API key (can also be set via CLAUDE_API_KEY environment variable)')
    
    args = parser.parse_args()
    
    if not args.api_key:
        raise ValueError("API key must be provided either via --api-key argument or CLAUDE_API_KEY environment variable")
    
    translator = SubtitleTranslator(args.api_key)
    translator.translate_subtitles(args.input, args.output, args.language)

if __name__ == "__main__":
    main()