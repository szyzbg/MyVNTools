import os
import csv
import json
import argparse
from pathlib import Path

def extract_mode(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith('.csv'):
                csv_path = os.path.join(root, file)
                relative_path = os.path.relpath(csv_path, input_dir)
                json_path = Path(output_dir) / Path(relative_path).with_suffix('.json')
                os.makedirs(json_path.parent, exist_ok=True)

                data = []
                with open(csv_path, 'r', encoding='cp932', newline='') as csvfile:
                    reader = csv.reader(csvfile)
                    try:
                        header = next(reader)
                    except StopIteration:
                        print(f"⚠️ 警告：文件 {csv_path} 为空，跳过处理。")
                        continue

                    name_idx = None
                    text_idx = None
                    for i, col in enumerate(header):
                        if col.strip() == '%name%':
                            name_idx = i
                        if col.strip() == '%text%':
                            text_idx = i

                    if text_idx is None:
                        print(f"⚠️ 警告：文件 {csv_path} 中未找到 %text% 列，跳过处理。")
                        continue

                    for row in reader:
                        if len(row) <= text_idx:
                            print(f"⚠️ 警告：文件 {csv_path} 的某行数据长度不足，跳过此行。")
                            continue

                        text_val = row[text_idx].strip()
                        if not text_val:
                            continue  # 跳过 text 为空的行

                        entry = {"message": row[text_idx]}
                        if name_idx is not None and name_idx < len(row):
                            name_val = row[name_idx].strip()
                            if name_val:
                                entry["name"] = name_val

                        data.append(entry)

                with open(json_path, 'w', encoding='utf-8') as jsonfile:
                    json.dump(data, jsonfile, ensure_ascii=False, indent=2)

                print(f"✅ 已提取：{csv_path} -> {json_path}")

def inject_mode(csv_dir, json_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for root, dirs, files in os.walk(csv_dir):
        for file in files:
            if file.lower().endswith('.csv'):
                csv_path = os.path.join(root, file)
                relative_path = os.path.relpath(csv_path, csv_dir)
                json_path = Path(json_dir) / Path(relative_path).with_suffix('.json')

                if not os.path.exists(json_path):
                    print(f"⚠️ 警告：对应的 JSON 文件不存在：{json_path}，跳过处理：{csv_path}")
                    continue

                try:
                    with open(csv_path, 'r', encoding='cp932', newline='') as csvfile:
                        reader = csv.reader(csvfile)
                        try:
                            header = next(reader)
                        except StopIteration:
                            print(f"⚠️ 警告：文件 {csv_path} 为空，跳过处理。")
                            continue
                        csv_rows = list(reader)
                except Exception as e:
                    print(f"❌ 读取 CSV 文件失败：{csv_path}，错误：{e}")
                    continue

                try:
                    with open(json_path, 'r', encoding='utf-8') as jsonfile:
                        json_data = json.load(jsonfile)
                except Exception as e:
                    print(f"❌ 读取 JSON 文件失败：{json_path}，错误：{e}")
                    continue

                name_idx = None
                text_idx = None
                for i, col in enumerate(header):
                    if col.strip() == '%name%':
                        name_idx = i
                    if col.strip() == '%text%':
                        text_idx = i

                if text_idx is None:
                    print(f"⚠️ 警告：文件 {csv_path} 中未找到 %text% 列，跳过处理。")
                    continue

                # 收集需要注入的有效行索引
                valid_csv_rows = []
                original_indices = []  # 记录这些行在原始 csv_rows 中的位置
                for idx, row in enumerate(csv_rows):
                    if len(row) > text_idx and row[text_idx].strip():
                        valid_csv_rows.append(row)
                        original_indices.append(idx)

                if len(valid_csv_rows) != len(json_data):
                    print(f"❌ 错误：CSV 文件 {csv_path} 和 JSON 文件 {json_path} 的有效行数不一致，跳过处理。")
                    continue

                # 修改对应的有效行
                updated_rows = list(csv_rows)  # 拷贝所有原始行
                for i, idx in enumerate(original_indices):
                    json_entry = json_data[i]
                    row = updated_rows[idx]

                    # 更新 name 列（如果有）
                    if name_idx is not None and name_idx < len(row) and 'name' in json_entry:
                        row[name_idx] = str(json_entry['name'])

                    # 总是更新 text 列
                    if text_idx < len(row):
                        row[text_idx] = str(json_entry.get('message', ''))

                # 写出结果
                output_csv_path = Path(output_dir) / Path(relative_path)
                os.makedirs(output_csv_path.parent, exist_ok=True)
                with open(output_csv_path, 'w', encoding='cp932', newline='') as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(header)
                    writer.writerows(updated_rows)

                print(f"✅ 已注入：{csv_path} -> {output_csv_path}")

def main():
    parser = argparse.ArgumentParser(description='从 CSV 提取翻译文本到 JSON 或将翻译后的内容回注到 CSV。')
    subparsers = parser.add_subparsers(dest='mode', required=True)

    extract_parser = subparsers.add_parser('extract', help='提取模式：从 CSV 生成 JSON')
    extract_parser.add_argument('--input_dir', required=True, help='包含 CSV 文件的输入目录')
    extract_parser.add_argument('--output_dir', required=True, help='输出 JSON 文件的目录')

    inject_parser = subparsers.add_parser('inject', help='回注模式：从 JSON 回注到 CSV')
    inject_parser.add_argument('--csv_dir', required=True, help='原始 CSV 文件的目录')
    inject_parser.add_argument('--json_dir', required=True, help='包含翻译后的 JSON 文件的目录')
    inject_parser.add_argument('--output_dir', required=True, help='输出注入后的 CSV 文件的目录')

    args = parser.parse_args()

    if args.mode == 'extract':
        extract_mode(args.input_dir, args.output_dir)
    elif args.mode == 'inject':
        inject_mode(args.csv_dir, args.json_dir, args.output_dir)
    else:
        print("❌ 错误：无效的模式，请使用 extract 或 inject。")

if __name__ == '__main__':
    main()