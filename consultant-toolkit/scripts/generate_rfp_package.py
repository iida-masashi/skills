import argparse
import os

from consultant_toolkit.rfp_generator import RFPGenerator


def main():
    parser = argparse.ArgumentParser(description="産業別ERP RFP作成3点セット生成ツール")
    parser.add_argument("--industry", type=str, required=True, help="産業名 (e.g. medical, general)")
    parser.add_argument("--output_dir", type=str, default="data/rfp_outputs", help="出力先ディレクトリ")

    args = parser.parse_args()

    # 絶対パスに変換
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_path = os.path.join(base_dir, args.output_dir)

    generator = RFPGenerator(output_path)
    prefix = generator.generate(args.industry)

    print(f"Success! RFP 3-item set generated for '{args.industry}':")
    print(f"Location: {output_path}")
    print(f"- {prefix}_Tasks.xlsx / .csv")
    print(f"- {prefix}_Evaluation.xlsx / .csv")
    print(f"- {prefix}_Draft_Prototype.md")

if __name__ == "__main__":
    main()
