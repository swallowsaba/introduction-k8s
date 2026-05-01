source "https://rubygems.org"

# GitHub Pagesのバージョンに合わせたGemを使用
gem "github-pages", group: :jekyll_plugins
gem "just-the-docs"

# プラグイン
group :jekyll_plugins do
  gem "jekyll-seo-tag"
  gem "jekyll-sitemap"
  gem "jekyll-remote-theme"
end

# Windows向け
platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", ">= 1", "< 3"
  gem "tzinfo-data"
end

gem "wdm", "~> 0.1.1", :platforms => [:mingw, :x64_mingw, :mswin]
gem "http_parser.rb", "~> 0.6.0", :platforms => [:jruby]

gem "webrick", "~> 1.7"
