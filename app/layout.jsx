import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

export const metadata = {
  title: "URL → Doc",
  description: "Save webpages as a single PDF or Markdown document.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://api.fontshare.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://api.fontshare.com/v2/css?f[]=general-sans@200,300,400,500,600,700&display=swap"
        />
      </head>
      <body>
        <TooltipProvider delayDuration={150}>{children}</TooltipProvider>
        <Toaster closeButton position="bottom-center" toastOptions={{ duration: 3500 }} />
      </body>
    </html>
  );
}
