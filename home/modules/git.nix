{ ... }: {
  #GIT
  programs.git = {
    enable = true;
  };

  programs.gh = {
    enable = true;

    settings = {
      git_protocol = "https";
    };

    gitCredentialHelper.enable = true;
  };
}
