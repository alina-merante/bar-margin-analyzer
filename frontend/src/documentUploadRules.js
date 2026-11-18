export const MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024;

export function isOversizedNonImage(file) {
  return (
    file.size > MAX_DOCUMENT_SIZE_BYTES &&
    !file.type.startsWith("image/")
  );
}

export function needsImageCompression(file) {
  return (
    file.size > MAX_DOCUMENT_SIZE_BYTES &&
    file.type.startsWith("image/")
  );
}
