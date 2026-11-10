export const MAX_PROGRAM_SOURCE_BYTES = 256 * 1024;

export function programFilesError(file: File | null, includes: File[]): string {
  if (file && !file.name.toLowerCase().endsWith('.littlefoot'))
    return 'choose a .littlefoot source file.';
  const files = file ? [file, ...includes] : includes;
  const names = new Set<string>();
  for (const item of files) {
    if (names.has(item.name)) return `duplicate filename: ${item.name}. choose each file once.`;
    names.add(item.name);
  }
  const filenameBytes = includes.reduce(
    (total, item) => total + new TextEncoder().encode(item.name).length,
    0,
  );
  if (files.reduce((total, item) => total + item.size, filenameBytes) > MAX_PROGRAM_SOURCE_BYTES)
    return 'the source and include files must total no more than 256 KiB.';
  return '';
}
