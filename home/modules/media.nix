{ ... }: {
  programs.yt-dlp = {
    enable = true;

    settings = {
      embed-thumbnail = true;
      add-metadata = true;
      paths = "/home/mihao/Documents/yt-dlp-dowloads";
    };
  };
}
