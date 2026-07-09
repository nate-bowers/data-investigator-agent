import { redirect } from "next/navigation";

// The viewer now lives at the site root. Keep this path working for any old links.
export default function InvestigatorRedirect() {
  redirect("/");
}
