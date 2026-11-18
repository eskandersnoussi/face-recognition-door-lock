"""Step 2 - Train the recogniser on everyone in dataset/.

    python train.py
"""
from doorlock.config import Settings
from doorlock.recognizer import train


def main() -> None:
    settings = Settings.from_env()
    counts = train(settings.dataset_dir, settings.model_path, settings.labels_path)
    for name, count in counts.items():
        print(f"  {name}: {count} images")
    print(f"Model saved to {settings.model_path}. Now run: python main.py")


if __name__ == "__main__":
    main()
