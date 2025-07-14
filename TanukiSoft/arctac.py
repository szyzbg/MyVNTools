import os
import zlib
import struct
import argparse
import random
from pathlib import Path
from collections import defaultdict
from Crypto.Cipher import Blowfish

# TAC文件签名和版本
SIGNATURE = b'TArc'
VERSION = b'1.10\0'
INDEX_KEY = b'TLibArchiveData'

class TacPacker:
    def __init__(self, input_dir, output_file):
        self.input_dir = Path(input_dir)
        self.output_file = Path(output_file)
        self.arc_seed = random.randint(0, 0xFFFFFFFF)
        self.entries = []
        self.buckets = []

    def hash_from_ascii_string(self, s, seed):
        """计算TanukiSoft风格的哈希值"""
        s = s.replace('\\', '/').upper()
        hash_val = 0
        for c in s:
            char_code = ord(c) & 0xFFFFFFFF
            hash_val = (char_code + 0x19919 * hash_val + seed) & 0xFFFFFFFFFFFFFFFF
        return hash_val

    def collect_files(self):
        """收集需要打包的文件"""
        for path in self.input_dir.rglob('*'):
            if path.is_file() and path.name != self.output_file.name and path.name != 'tanuki.lst':
                rel_path = path.relative_to(self.input_dir).as_posix()
                self.entries.append({
                    'path': path,
                    'rel_path': rel_path,
                    'full_hash': None,
                    'bucket_hash': None,
                    'entry_hash_low': None,
                    'is_packed': True,
                    'unpacked_size': 0,
                    'size': 0,
                    'offset': 0,
                    'encrypted_size': 0,
                    'data': None
                })

    def process_files(self):
        """处理文件数据（压缩）"""
        current_offset = 0
        for entry in self.entries:
            with open(entry['path'], 'rb') as f:
                data = f.read()
            entry['unpacked_size'] = len(data)
            
            # 压缩文件
            compressed_data = zlib.compress(data, 9)
            entry['size'] = len(compressed_data)
            entry['offset'] = current_offset
            entry['data'] = compressed_data
            current_offset += len(compressed_data)
            
            # 计算哈希
            full_hash = self.hash_from_ascii_string(entry['rel_path'], self.arc_seed)
            entry['full_hash'] = full_hash
            entry['bucket_hash'] = (full_hash >> 48) & 0xFFFF
            entry['entry_hash_low'] = full_hash & 0xFFFFFFFFFFFF

    def build_buckets(self):
        """构建bucket表"""
        bucket_dict = defaultdict(list)
        for entry in self.entries:
            bucket_dict[entry['bucket_hash']].append(entry)
            
        # 按bucket hash排序
        sorted_buckets = sorted(bucket_dict.items())
        self.buckets = []
        current_index = 0
        
        for bh, entries_in_bucket in sorted_buckets:
            self.buckets.append({
                'Hash': bh,
                'Count': len(entries_in_bucket),
                'Index': current_index,
            })
            current_index += len(entries_in_bucket)
            
        # 按bucket排序重新排列entries
        self.entries.sort(key=lambda e: (e['bucket_hash'], e['entry_hash_low']))

    def build_index(self):
        """构建索引数据"""
        index_data = bytearray()
        
        # 写入buckets
        for b in self.buckets:
            index_data += struct.pack('<HHI', b['Hash'], b['Count'], b['Index'])
        
        # 写入entries
        for e in self.entries:
            hash_low = e['entry_hash_low']
            is_packed = 1 if e['is_packed'] else 0
            offset = e['offset']  # 这个值会在写入文件时重新计算
            
            index_data += struct.pack(
                '<QIIII',
                hash_low,
                is_packed,
                e['unpacked_size'],
                offset,
                e['size']
            )
        
        return bytes(index_data)

    def write_archive(self):
        """写入最终文件"""
        # 处理文件数据
        self.collect_files()
        self.process_files()
        self.build_buckets()
        
        # 构建索引数据
        index_data = self.build_index()
        
        # 压缩索引数据
        compressed_index = zlib.compress(index_data, 9)
        
        # Blowfish加密索引数据
        cipher = Blowfish.new(INDEX_KEY, Blowfish.MODE_ECB)
        pad_len = (8 - (len(compressed_index) % 8)) % 8
        encrypted_index = cipher.encrypt(compressed_index + b'\0' * pad_len)
        index_size = len(encrypted_index)
        
        # 计算base_offset
        base_offset = 0x2C + index_size
        
        # 更新entries的offset
        current_offset = base_offset
        for e in self.entries:
            e['offset'] = current_offset
            current_offset += len(e['data'])
        
        # 重新构建包含正确offset的索引
        index_data = self.build_index()
        compressed_index = zlib.compress(index_data, 9)
        encrypted_index = cipher.encrypt(compressed_index + b'\0' * ((8 - len(compressed_index) % 8) % 8))
        
        # 写入文件
        with open(self.output_file, 'wb') as f:
            # 写入签名和版本
            f.write(SIGNATURE)
            f.write(VERSION)
            
            # 写入头部信息
            f.write(struct.pack('<IIII', len(self.entries), len(self.buckets), index_size, self.arc_seed))
            
            # 填充到0x2C
            f.seek(0x2C)
            
            # 写入加密的索引数据
            f.write(encrypted_index)
            
            # 写入文件数据
            for e in self.entries:
                f.write(e['data'])

def main():
    parser = argparse.ArgumentParser(description='Pack directory into TAC archive')
    parser.add_argument('input_dir', help='Directory to pack')
    parser.add_argument('output_file', help='Output TAC file')
    args = parser.parse_args()
    
    packer = TacPacker(args.input_dir, args.output_file)
    packer.write_archive()
    print(f"Successfully created TAC archive at {args.output_file}")

if __name__ == '__main__':
    main()