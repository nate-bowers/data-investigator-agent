import { redirect } from "next/navigation";

// No landing gate: go straight to the viewer.
export default function Home() {
  redirect("/investigator");
}
