import Link from "next/link";
import { PageHead } from "@/components/ui";

export default function NotFound() {
  return (
    <>
      <PageHead title="Page not found" lede="This page is not part of the release log. The address can be old, or it can have a typing error." />
      <p>
        <Link className="button" href="/">
          Go to the release log
        </Link>
      </p>
    </>
  );
}
