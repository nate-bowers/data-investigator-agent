import Link from "next/link";

export default function Home() {
  return (
    <main style={{ padding: 32 }}>
      <h1>Data Investigator</h1>
      <p>
        <Link href="/investigator">→ Open the investigation viewer</Link>
      </p>
    </main>
  );
}
