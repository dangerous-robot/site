---
title: Turn Off AI You Didn't Ask For
description: Step-by-step guides to disable Meta AI, Google AI Overviews, and Microsoft Copilot. What works, what doesn't, and what to try next.
pubDate: 2026-03-04
layout: guide
wallpaper: none
topics:
  - consumer-guide
  - ai-literacy
data:
  platforms:
    - id: meta-ai
      name: Meta AI
      where_it_shows: WhatsApp, Instagram, Facebook, Messenger
      context: |
        Meta reported one billion monthly active users in 2025. Most of those users didn't subscribe to an AI service, Meta AI ships inside WhatsApp, Instagram, and Messenger by default. You can't fully remove it from Meta's apps, but you can reduce how often it appears.
      sub_sections:
        - title: WhatsApp
          steps:
            - "Open any chat with \"Meta AI\" or tap the Meta AI icon in the search bar."
            - "Tap the Meta AI name at the top of the conversation."
            - "Select **Mute** or **Delete chat**."
            - "To block it entirely: tap **Block** on the Meta AI profile page."
          post_note: "Blocking Meta AI in WhatsApp prevents it from responding in that chat. It does not remove the icon from the search bar."
        - title: Instagram
          steps:
            - "If Meta AI appears in your DMs, open the conversation."
            - "Tap the Meta AI name at the top."
            - "Select **Delete Chat**."
            - "To limit AI suggestions in Search: there is no toggle. Avoid tapping the \"Ask Meta AI\" prompt and it will appear less frequently."
        - title: Facebook
          steps:
            - "Open Messenger and find any Meta AI chat."
            - "Long-press the conversation and select **Delete**."
            - "On Facebook Search: there is no option to disable the Meta AI prompt. It is baked into the search experience."
      what_doesnt_work: |
        There is no global "turn off Meta AI" setting in any Meta app, and Meta has not indicated plans to add one. Blocking Meta AI in individual apps also does not prevent Meta from using your data to train its AI models, that requires a separate data request through Meta's privacy settings, and availability varies by region.
      last_verified: "2026-04-01"
      last_verified_label: April 2026
    - id: google
      name: Google AI Overviews
      where_it_shows: Google Search (desktop and mobile browsers, Google app)
      context: |
        Google AI Overviews are the AI-generated summaries that appear above search results. Google handles roughly 90% of global searches, making this the most widely encountered AI feature on the internet. Google does not provide a toggle to disable them.
      sub_sections:
        - title: Workarounds
          steps:
            - "**Add `&udm=14` to any Google search URL.** This forces \"Web\" mode and suppresses AI Overviews. Bookmark `https://www.google.com/search?udm=14&q=` as your default search to apply it automatically. [Setup walkthrough on r/TechSEO](https://www.reddit.com/r/TechSEO/comments/1rit73c/udm14_how_to_get_old_school_google_back_by/)."
            - "**Use the \"Web\" tab.** After any Google search, click the **Web** filter below the search bar. This shows traditional results without AI summaries."
            - "**Install the [\"Bye Bye Google AI\"](https://chromewebstore.google.com/detail/imllolhfajlbkpheaapjocclpppchggc?utm_source=item-share-cb) browser extension.** Available for Chrome, Edge, and Firefox (60,000+ installs). It automatically filters AI Overviews from results."
            - "**Switch your default search engine.** DuckDuckGo, Startpage, and Kagi (paid) do not inject AI summaries into results. All major browsers let you change the default in Settings > Search Engine."
      what_doesnt_work: |
        There is no setting in your Google Account to disable AI Overviews. Google has characterized AI as fundamental to the modern search experience and has given no indication it plans to add a user-facing toggle.
      last_verified: "2026-04-01"
      last_verified_label: April 2026
    - id: copilot
      name: Microsoft Copilot
      where_it_shows: Windows 11 (taskbar, Start menu, Settings, Edge, File Explorer)
      context: |
        Copilot is the AI feature that keeps coming back after you remove it. Hiding the taskbar button does not disable it. It reinstalls itself after Windows updates. Kaspersky's guide notes that you may need to check periodically for a couple of months after removal to make sure it stays gone.
      sub_sections:
        - title: Windows 11 Home
          preamble: "No Group Policy editor on Home edition, so you need the registry."
          steps:
            - "Press **Win + R**, type `regedit`, press Enter."
            - "Navigate to `HKEY_CURRENT_USER\\Software\\Policies\\Microsoft\\Windows\\WindowsCopilot`."
            - "If the `WindowsCopilot` key doesn't exist, right-click `Windows` > **New > Key** and name it `WindowsCopilot`."
            - "Right-click in the right pane > **New > DWORD (32-bit) Value**. Name it `TurnOffWindowsCopilot`."
            - "Double-click the new value and set it to `1`."
            - "Restart your computer."
        - title: Windows 11 Pro / Enterprise
          steps:
            - "Press **Win + R**, type `gpedit.msc`, press Enter."
            - "Navigate to **User Configuration > Administrative Templates > Windows Components > Windows Copilot**."
            - "Double-click **Turn off Windows Copilot** and set it to **Enabled**."
            - "Click **Apply**, then restart."
          post_note: "Microsoft has announced plans to retire this Group Policy setting. On Windows 11 24H2 and later, both the Group Policy and registry settings may only disable the legacy Copilot sidebar, not the standalone Copilot app. The app removal steps below are now the more reliable approach."
        - title: Removing the Copilot app
          preamble: "Even after disabling via policy or registry, the Copilot app may remain installed."
          steps:
            - "Open **Settings > Apps > Installed apps**."
            - "Search for \"Copilot.\""
            - "Click the three-dot menu and select **Uninstall**."
            - "If Uninstall is grayed out, open PowerShell as Administrator and run: `Get-AppxPackage -Name *Microsoft.Copilot* | Remove-AppxPackage`"
        - title: Preventing reinstallation
          steps:
            - "Open **Microsoft Store > Settings** (your profile icon, top right)."
            - "Turn off **App updates** to prevent Copilot from silently reinstalling via Store auto-updates. (This also stops other app updates, so weigh the tradeoff.)"
            - "After major Windows updates (monthly cumulative or feature updates), check Settings > Apps to confirm Copilot hasn't returned."
      what_doesnt_work: |
        Right-clicking the taskbar and unchecking "Copilot" only hides the button. The feature remains active in the background.
      last_verified: "2026-04-01"
      last_verified_label: April 2026
  further_reading:
    - title: How to Turn Off AI Tools
      url: "https://www.consumerreports.org/electronics/artificial-intelligence/turn-off-ai-tools-gemini-apple-intelligence-copilot-and-more-a1156421356/"
      source: Consumer Reports
      description: "Multi-platform guide covering Apple, Google, Meta, Microsoft, and Samsung. The most thorough single resource available."
    - title: How to Switch Off AI
      url: "https://www.kaspersky.com/blog/how-to-switch-off-ai/55383/"
      source: Kaspersky
      description: "Covers Chrome, Gmail, Google Docs, and Windows Copilot. Notes Copilot's silent reinstallation behavior."
    - title: "Google, Microsoft, Meta All Tracking You Even When You Opt Out"
      url: "https://www.404media.co/google-microsoft-meta-all-tracking-you-even-when-you-opt-out-according-to-an-independent-audit/"
      source: 404 Media
      description: "According to a webXray audit of 7,000+ websites, Google ignored browser privacy opt-out signals (GPC) 87% of the time, Meta 69%, Microsoft 50%. Turning things off is one step. Verifying they stay off is another."
---

AI now ships inside your messaging apps, your search engine, and your
operating system, often without asking. Here's how to take it back out.
