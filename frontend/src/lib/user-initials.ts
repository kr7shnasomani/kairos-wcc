export function getUserInitials(email?: string): string {
  const localPart = email?.split("@", 1)[0] ?? "Kairos";
  const words = localPart.split(/[^a-zA-Z0-9]+/).filter(Boolean);

  if (words.length > 1) {
    return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  }

  return localPart.slice(0, 2).toUpperCase();
}
